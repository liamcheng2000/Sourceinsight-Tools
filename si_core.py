"""Source Insight 文件清单生成核心逻辑。

从 Xilinx/Vitis（Eclipse CDT）构建目录中的 subdir.mk 与 GCC 依赖文件（*.d）
提取真实参与编译的源文件和头文件，生成 Source Insight 可直接导入的清单。

本模块不依赖任何 GUI，可单独测试或复用。
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable

APP_NAME = "Source Insight 文件清单生成器"
APP_VERSION = "1.0.0"
SI_VERSION = "4.00.0150"

SOURCE_EXTENSIONS = {".c", ".cc", ".cpp", ".cxx", ".s", ".asm"}
HEADER_EXTENSIONS = {".h", ".hh", ".hpp", ".hxx", ".inc", ".inl"}

SOURCE_VARS = (
    "C_SRCS",
    "CPP_SRCS",
    "CXX_SRCS",
    "CC_SRCS",
    "ASM_SRCS",
    "S_UPPER_SRCS",
)

_ASSIGN_RE = re.compile(
    r"^(?P<var>" + "|".join(SOURCE_VARS) + r")\s*(?:\+=|:=|\?=|=)\s*(?P<rhs>.*)$"
)
_INVALID_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

LogFn = Callable[[str, str], None]

_ESCAPED_SPACE = "\x00SI_ESCAPED_SPACE\x00"


class SIError(Exception):
    """可直接展示给用户的错误。"""


@dataclass
class GenerateResult:
    project_folder: str
    si_project_name: str
    source_root: str
    build_dir: str
    source_count: int
    header_count: int
    listed_count: int
    outside_count: int
    output_file: str
    outside_file: str | None = None
    warnings: list[str] = field(default_factory=list)


def default_si_name(project_folder: str) -> str:
    """根据 Xilinx 工程名推导默认的 Source Insight 工程名。"""
    name = os.path.basename(os.path.normpath(project_folder))
    if name.lower().startswith("prj_"):
        name = name[4:]
    return "SI_" + (name or "Project")


def _logger(logger: LogFn | None) -> LogFn:
    def log(message: str, level: str = "info") -> None:
        if logger is not None:
            logger(message, level)

    return log


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _split_make_tokens(text: str) -> list[str]:
    """按 make 规则切分路径，保留 ``\\ `` 形式的转义空格。"""
    protected = text.replace("\\ ", _ESCAPED_SPACE).replace("\\\t", _ESCAPED_SPACE)
    tokens: list[str] = []
    for raw in protected.split():
        token = raw.replace(_ESCAPED_SPACE, " ").strip()
        if token:
            tokens.append(token)
    return tokens


def normalize_path(raw: str, base_dir: str) -> str | None:
    """把构建文件中的路径规范化为绝对路径；遇到 Make 变量时返回 None。"""
    if not raw:
        return None

    path = raw.strip().strip('"').strip("'")
    path = path.replace("\\ ", " ").strip()
    path = path.rstrip("\\")

    if not path or "$(" in path or "${" in path:
        return None

    try:
        if not os.path.isabs(path):
            path = os.path.join(base_dir, path)
        return os.path.normpath(path)
    except (OSError, ValueError):
        return None


def _iter_logical_lines(path: str) -> Iterable[str]:
    """读取 makefile，合并以反斜杠结尾的续行。"""
    parts: list[str] = []
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\r\n")
            trimmed = line.rstrip()
            if trimmed.endswith("\\"):
                parts.append(trimmed[:-1].strip())
                continue

            parts.append(line.strip())
            joined = " ".join(part for part in parts if part)
            if joined:
                yield joined
            parts.clear()

    if parts:
        joined = " ".join(part for part in parts if part)
        if joined:
            yield joined


def _walk_named(root: str, filename: str) -> list[str]:
    found: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        if any(name.lower() == filename.lower() for name in filenames):
            found.append(os.path.join(dirpath, filename))
    found.sort(key=str.casefold)
    return found


def _walk_extensions(root: str, extensions: set[str]) -> list[str]:
    found: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        for name in filenames:
            if os.path.splitext(name)[1].lower() in extensions:
                found.append(os.path.join(dirpath, name))
    found.sort(key=str.casefold)
    return found


def _contains_subdir_mk(root: str, max_depth: int = 4) -> bool:
    """限制深度快速判断目录内是否存在 subdir.mk。"""
    try:
        base_depth = os.path.abspath(root).rstrip(os.sep).count(os.sep)
    except OSError:
        return False

    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        depth = os.path.abspath(dirpath).rstrip(os.sep).count(os.sep) - base_depth
        if depth >= max_depth:
            dirnames[:] = []
        if any(name.lower() == "subdir.mk" for name in filenames):
            return True
    return False


def _looks_like_build_project(project_dir: str) -> bool:
    """判断目录是否像一个已构建工程：直接子目录中能找到 subdir.mk。"""
    try:
        with os.scandir(project_dir) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False) and _contains_subdir_mk(entry.path):
                    return True
    except OSError:
        return False
    return False


def list_projects(trunk_dir: str) -> list[str]:
    """列出工作区中的 Xilinx 工程：Prj_* 优先，其次是看起来已构建的目录。"""
    if not trunk_dir or not os.path.isdir(trunk_dir):
        return []

    try:
        with os.scandir(trunk_dir) as entries:
            dirs = sorted(
                (
                    entry
                    for entry in entries
                    if entry.is_dir(follow_symlinks=False) and not entry.name.startswith(".")
                ),
                key=lambda entry: entry.name.casefold(),
            )
    except OSError:
        return []

    primary: list[str] = []
    secondary: list[str] = []
    for entry in dirs:
        if entry.name.lower().startswith("prj_"):
            primary.append(entry.name)
        elif _looks_like_build_project(entry.path):
            secondary.append(entry.name)

    return primary + secondary


def find_build_configs(project_dir: str) -> list[str]:
    """列出工程下包含 subdir.mk 的构建配置目录（如 Debug、Release）。"""
    if not project_dir or not os.path.isdir(project_dir):
        return []

    try:
        with os.scandir(project_dir) as entries:
            dirs = sorted(
                (entry for entry in entries if entry.is_dir(follow_symlinks=False)),
                key=lambda entry: entry.name.casefold(),
            )
    except OSError:
        return []

    return [entry.name for entry in dirs if _contains_subdir_mk(entry.path)]


def _collect_sources(build_dir: str, log: LogFn) -> dict[str, str]:
    subdir_files = _walk_named(build_dir, "subdir.mk")
    log(f"发现 {len(subdir_files)} 个 subdir.mk", "info")
    if not subdir_files:
        raise SIError(
            "未找到 subdir.mk，无法确定实际参与编译的文件。\n\n"
            "请先完整编译一次工程，并确认构建配置目录选择正确。"
        )

    sources: dict[str, str] = {}
    skipped = 0

    for makefile in subdir_files:
        try:
            lines = _iter_logical_lines(makefile)
            for line in lines:
                match = _ASSIGN_RE.match(line.strip())
                if not match:
                    continue

                for token in _split_make_tokens(match.group("rhs")):
                    path = normalize_path(token, build_dir)
                    if path is None:
                        if "$(" in token or "${" in token:
                            skipped += 1
                        continue

                    if os.path.splitext(path)[1].lower() not in SOURCE_EXTENSIONS:
                        continue
                    if not os.path.isfile(path):
                        continue

                    sources.setdefault(os.path.normcase(path), path)
        except OSError as exc:
            log(f"读取失败：{makefile}（{exc}）", "warn")

    if skipped:
        log(f"已忽略 {skipped} 个使用 Make 变量的源文件路径（无法解析）", "warn")

    return sources


def _collect_headers(build_dir: str, log: LogFn) -> tuple[dict[str, str], int]:
    dep_files = _walk_extensions(build_dir, {".d"})
    log(f"发现 {len(dep_files)} 个依赖文件（*.d）", "info")

    headers: dict[str, str] = {}
    skipped = 0

    for dep_file in dep_files:
        try:
            text = _read_text(dep_file)
        except OSError:
            continue

        text = text.replace("\\\r\n", " ").replace("\\\n", " ").replace("\\\r", " ")

        match = re.search(r":\s", text)
        if not match:
            continue

        for token in _split_make_tokens(text[match.end():]):
            path = normalize_path(token, build_dir)
            if path is None:
                if "$(" in token or "${" in token:
                    skipped += 1
                continue

            if os.path.splitext(path)[1].lower() not in HEADER_EXTENSIONS:
                continue
            if not os.path.isfile(path):
                continue

            headers.setdefault(os.path.normcase(path), path)

    if skipped:
        log(f"已忽略 {skipped} 个使用 Make 变量的头文件路径（无法解析）", "warn")

    return headers, len(dep_files)


def _relative_to(path: str, root: str) -> str | None:
    """若 path 位于 root 之下，返回反斜杠分隔的相对路径。"""
    try:
        path_norm = os.path.normcase(os.path.abspath(path))
        root_norm = os.path.normcase(os.path.abspath(root))
        if os.path.commonpath([path_norm, root_norm]) != root_norm:
            return None
        return os.path.relpath(path, root).replace(os.sep, "\\")
    except (OSError, ValueError):
        return None


def _write_text(path: str, content: str) -> None:
    """原子写入，使用 UTF-8 BOM + CRLF，兼容 Source Insight 和 Windows 工具。"""
    directory = os.path.dirname(path) or "."
    fd, temp_path = tempfile.mkstemp(prefix=".si_filelist_", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            handle.write(content)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def generate_filelist(
    trunk_dir: str,
    project_folder: str,
    source_root: str = "CtrlSW",
    config: str = "Debug",
    si_project_name: str = "",
    logger: LogFn | None = None,
) -> GenerateResult:
    """生成 Source Insight 文件清单。

    参数：
        trunk_dir: 工作区根目录（包含 Xilinx 工程和源码根目录）。
        project_folder: 工程目录，可相对于 trunk_dir，也可为绝对路径。
        source_root: 源码根目录，可相对于 trunk_dir，也可为绝对路径。
        config: 构建配置目录名，如 Debug / Release。
        si_project_name: Source Insight 工程名；为空时自动推导。
        logger: 日志回调 ``logger(message, level)``。
    """
    log = _logger(logger)

    if not trunk_dir or not trunk_dir.strip():
        raise SIError("请选择工作区目录。")

    trunk = os.path.abspath(trunk_dir.strip())
    if not os.path.isdir(trunk):
        raise SIError(f"工作区不存在：\n{trunk}")

    project_folder = (project_folder or "").strip()
    if not project_folder:
        raise SIError("请选择或输入 Xilinx 工程。")

    project_dir = (
        project_folder
        if os.path.isabs(project_folder)
        else os.path.join(trunk, project_folder)
    )
    project_dir = os.path.abspath(project_dir)
    if not os.path.isdir(project_dir):
        raise SIError(f"工程目录不存在：\n{project_dir}")

    config = (config or "").strip() or "Debug"
    build_dir = os.path.join(project_dir, config)
    if not os.path.isdir(build_dir):
        raise SIError(
            f"构建目录不存在：\n{build_dir}\n\n"
            f"请先使用 {config} 配置完整编译一次工程。"
        )

    source_root = (source_root or "").strip() or "CtrlSW"
    source_root_dir = (
        source_root if os.path.isabs(source_root) else os.path.join(trunk, source_root)
    )
    source_root_dir = os.path.abspath(source_root_dir)
    if not os.path.isdir(source_root_dir):
        raise SIError(f"源码根目录不存在：\n{source_root_dir}")

    if not si_project_name or not si_project_name.strip():
        si_project_name = default_si_name(project_folder)
    si_project_name = si_project_name.strip()

    if _INVALID_NAME_RE.search(si_project_name):
        raise SIError('SI 工程名称包含非法字符（不能包含 < > : " / \\ | ? *）。')
    if si_project_name.endswith("."):
        raise SIError("SI 工程名称不能以句点结尾。")

    log(f"工程目录：{project_dir}", "path")
    log(f"构建目录：{build_dir}", "path")
    log(f"源码根目录：{source_root_dir}", "path")

    sources = _collect_sources(build_dir, log)
    headers, dep_count = _collect_headers(build_dir, log)

    if not sources:
        raise SIError(
            "未能从 subdir.mk 中提取到任何有效源文件。\n"
            "请确认工程已成功编译，且构建配置选择正确。"
        )

    warnings: list[str] = []
    if dep_count == 0:
        warnings.append(
            "未找到 .d 依赖文件，头文件不会被加入清单。"
            "请确认编译器启用了依赖生成（-MMD / -MP）。"
        )
    if not headers:
        warnings.append("未找到任何实际使用的头文件。")

    all_files: dict[str, str] = {}
    all_files.update(sources)
    all_files.update(headers)

    inside: list[str] = []
    outside: list[str] = []

    for path in sorted(all_files.values(), key=str.casefold):
        relative = _relative_to(path, source_root_dir)
        if relative is None:
            outside.append(path)
        else:
            inside.append(relative)

    inside.sort(key=str.casefold)
    outside.sort(key=str.casefold)

    log(f"源文件：{len(sources)} 个；头文件：{len(headers)} 个", "info")
    log(f"纳入清单：{len(inside)} 个；清单外：{len(outside)} 个", "info")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header_lines = [
        "; Source Insight Project File List",
        f"; Project Name: {si_project_name}",
        f"; Xilinx Project: {os.path.basename(project_dir)}",
        f"; Build Config: {config}",
        f"; Source Root: {source_root_dir}",
        f"; Generated by {APP_NAME} {APP_VERSION} at {timestamp}",
        f"; Version={SI_VERSION}",
        ";",
        "; Each line should contain either a file name, a wildcard, or a sub-directory name.",
        "; File paths are relative to the project source root directory.",
        ";",
    ]

    output_file = os.path.join(trunk, f"{si_project_name}_filelist.txt")
    _write_text(output_file, "\r\n".join(header_lines + inside) + "\r\n")
    log(f"已生成清单：{output_file}", "success")

    outside_file: str | None = None
    if outside:
        outside_file = os.path.join(trunk, f"{si_project_name}_outside_root.txt")
        outside_lines = [
            "; Files used by the build but outside the selected Source Insight source root:",
            f"; Source root: {source_root_dir}",
            "; These files are NOT written into the Source Insight file list.",
            ";",
        ]
        _write_text(outside_file, "\r\n".join(outside_lines + outside) + "\r\n")
        log(f"清单外文件：{outside_file}", "warn")
    else:
        stale_file = os.path.join(trunk, f"{si_project_name}_outside_root.txt")
        if os.path.isfile(stale_file):
            try:
                os.remove(stale_file)
                log("已删除上次遗留的 *_outside_root.txt", "muted")
            except OSError as exc:
                log(f"无法删除旧文件：{stale_file}（{exc}）", "warn")

    log(
        "提示：请在 Source Insight 工程中将源码根目录设置为上面显示的源码根目录。",
        "muted",
    )

    return GenerateResult(
        project_folder=project_dir,
        si_project_name=si_project_name,
        source_root=source_root_dir,
        build_dir=build_dir,
        source_count=len(sources),
        header_count=len(headers),
        listed_count=len(inside),
        outside_count=len(outside),
        output_file=output_file,
        outside_file=outside_file,
        warnings=warnings,
    )
