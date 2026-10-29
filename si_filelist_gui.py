"""Source Insight 文件清单生成器（图形界面）。

从 Xilinx/Vitis 构建产物生成 Source Insight 工程文件清单。
"""

from __future__ import annotations

import ctypes
import json
import os
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import traceback
from tkinter import filedialog, messagebox, ttk

from si_core import (
    APP_NAME,
    APP_VERSION,
    GenerateResult,
    SIError,
    default_si_name,
    find_build_configs,
    generate_filelist,
    list_projects,
)

BG = "#f3f5f8"
HEADER_BG = "#16324f"
HEADER_SUB = "#b9c9da"
ACCENT = "#1f6feb"
ACCENT_HOVER = "#2f81f7"
ACCENT_DISABLED = "#93a9c4"
HINT = "#667085"
STATUS = "#475467"
LOG_BG = "#0d1726"
LOG_FG = "#d7e3f2"
LOG_MUTED = "#7d8ca3"
LOG_SUCCESS = "#3ddc97"
LOG_WARN = "#f5b544"
LOG_ERROR = "#ff7b72"
LOG_PATH = "#79c0ff"

HELP_RESOURCE = "help.html"
HELP_TARGET_NAME = "使用教程.html"


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", app_dir())
    return os.path.join(base, name)


def settings_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "SourceInsightFileList")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "settings.json")


def help_target_path() -> str:
    return os.path.join(os.path.dirname(settings_path()), HELP_TARGET_NAME)


def prepare_help_file() -> str:
    """把内置教程复制到可长期访问的目录，返回目标路径。"""
    source = resource_path(HELP_RESOURCE)
    if not os.path.isfile(source):
        raise SIError("未找到内置使用教程，请重新获取完整程序。")

    target = help_target_path()
    try:
        shutil.copyfile(source, target)
    except OSError as exc:
        raise SIError(f"无法准备使用教程文件：\n{exc}") from exc
    return target


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def is_inside(path: str, root: str) -> bool:
    try:
        path_norm = os.path.normcase(os.path.abspath(path))
        root_norm = os.path.normcase(os.path.abspath(root))
        return os.path.commonpath([path_norm, root_norm]) == root_norm
    except (OSError, ValueError):
        return False


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title(f"{APP_NAME}  v{APP_VERSION}")
        self._center_window(980, 760)
        self.minsize(
            min(int(840 * self._dpi_scale), max(720, self.winfo_screenwidth() - 120)),
            min(int(600 * self._dpi_scale), max(560, self.winfo_screenheight() - 140)),
        )

        icon = resource_path("app.ico")
        if os.path.isfile(icon):
            try:
                self.iconbitmap(icon)
            except tk.TclError:
                pass

        families = set(tkfont.families(self))
        self.ui_font = "Microsoft YaHei UI" if "Microsoft YaHei UI" in families else "Segoe UI"
        self.mono_font = (
            "Cascadia Mono"
            if "Cascadia Mono" in families
            else ("Consolas" if "Consolas" in families else "Courier New")
        )

        self._busy = False
        self._last_result: GenerateResult | None = None
        self._queue: queue.Queue = queue.Queue()
        self._start_time = 0.0
        self._auto_si_value = ""

        self.trunk_var = tk.StringVar()
        self.project_var = tk.StringVar()
        self.config_var = tk.StringVar(value="Debug")
        self.source_var = tk.StringVar(value="CtrlSW")
        self.si_name_var = tk.StringVar()
        self.output_hint_var = tk.StringVar()
        self.status_var = tk.StringVar(value="就绪")
        self.auto_open_var = tk.BooleanVar(value=False)

        self._configure_style()
        self._build_ui()

        self.si_name_var.trace_add("write", self._refresh_output_hint)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<F5>", self.start_generate)
        self.bind("<F1>", self.open_help)

        self._load_settings()
        self.refresh_projects()
        if not self.project_var.get().strip():
            values = list(self.project_combo["values"])
            if values:
                self.project_var.set(values[0])
        self.on_project_changed()

        self.log(f"欢迎使用 {APP_NAME} v{APP_VERSION}", "success")
        self.log("请先完整编译一次 Xilinx 工程，再点击“生成文件清单”。", "muted")
        self.log(f"输出目录：{self._trunk_path() or app_dir()}", "path")

    # ------------------------------------------------------------------ UI

    def _center_window(self, width: int, height: int) -> None:
        try:
            self._dpi_scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        except tk.TclError:
            self._dpi_scale = 1.0

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        width = int(width * self._dpi_scale)
        height = int(height * self._dpi_scale)
        width = min(width, max(720, int(screen_w * 0.94)))
        height = min(height, max(560, int(screen_h * 0.90)))

        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - int(24 * self._dpi_scale))
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _configure_style(self) -> None:
        self.configure(bg=BG)
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        style.configure("TFrame", background=BG)
        style.configure("TLabelframe", background=BG)
        style.configure("TLabelframe.Label", background=BG, foreground=HEADER_BG)
        style.configure("TLabel", background=BG, foreground="#1f2937", font=(self.ui_font, 10))
        style.configure("Labelframe.Label", font=(self.ui_font, 10, "bold"))
        style.configure("TLabelframe.Label", font=(self.ui_font, 10, "bold"))
        style.configure("Hint.TLabel", foreground=HINT, font=(self.ui_font, 9))
        style.configure("Status.TLabel", foreground=STATUS, font=(self.ui_font, 9))
        style.configure("TButton", font=(self.ui_font, 9))
        style.configure("TCheckbutton", background=BG, font=(self.ui_font, 9))
        style.configure("TEntry", font=(self.ui_font, 10))
        style.configure("TCombobox", font=(self.ui_font, 10))
        style.map("TCombobox", fieldbackground=[("readonly", "white")])

    def _build_ui(self) -> None:
        header = tk.Frame(self, bg=HEADER_BG)
        header.pack(side="top", fill="x")

        header_inner = tk.Frame(header, bg=HEADER_BG)
        header_inner.pack(fill="x", padx=22, pady=(14, 12))

        tk.Label(
            header_inner,
            text=APP_NAME,
            bg=HEADER_BG,
            fg="white",
            font=(self.ui_font, 17, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            header_inner,
            text="从 Xilinx / Vitis 构建产物提取真实编译单元，一键生成 Source Insight 工程清单",
            bg=HEADER_BG,
            fg=HEADER_SUB,
            font=(self.ui_font, 9),
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))
        tk.Label(
            header_inner,
            text=f"v{APP_VERSION}",
            bg=HEADER_BG,
            fg="#7f9bb5",
            font=(self.ui_font, 9),
        ).place(relx=1.0, y=0, anchor="ne")

        tk.Frame(self, bg=ACCENT, height=3).pack(side="top", fill="x")

        status_bar = ttk.Frame(self, padding=(22, 0, 22, 10))
        status_bar.pack(side="bottom", fill="x")
        ttk.Label(status_bar, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        self.progress = ttk.Progressbar(status_bar, mode="indeterminate", length=170)

        main = ttk.Frame(self, padding=(22, 14, 22, 8))
        main.pack(fill="both", expand=True)

        form = ttk.LabelFrame(main, text=" 工程参数 ", padding=(14, 10, 14, 12))
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        self.trunk_entry = ttk.Entry(form, textvariable=self.trunk_var)
        self._add_form_row(
            form,
            0,
            "工作区",
            self.trunk_entry,
            button_text="浏览…",
            button_command=self.browse_trunk,
        )
        self.trunk_entry.bind("<FocusOut>", self._on_trunk_focus_out)
        self.trunk_entry.bind("<Return>", self._on_trunk_focus_out)

        self.project_combo = ttk.Combobox(form, textvariable=self.project_var, state="normal")
        self._add_form_row(
            form,
            1,
            "Xilinx 工程",
            self.project_combo,
            button_text="浏览…",
            button_command=self.browse_project,
        )
        self.project_combo.bind("<<ComboboxSelected>>", self.on_project_changed)
        self.project_combo.bind("<FocusOut>", self.on_project_changed)
        self.project_combo.bind("<Return>", self.on_project_changed)

        self.config_combo = ttk.Combobox(form, textvariable=self.config_var, state="normal")
        self._add_form_row(
            form,
            2,
            "构建配置",
            self.config_combo,
            hint="Debug / Release",
        )

        self.source_combo = ttk.Combobox(form, textvariable=self.source_var, state="normal")
        self._add_form_row(
            form,
            3,
            "源码根目录",
            self.source_combo,
            button_text="浏览…",
            button_command=self.browse_source_root,
        )

        self.si_entry = ttk.Entry(form, textvariable=self.si_name_var)
        self._add_form_row(
            form,
            4,
            "SI 工程名称",
            self.si_entry,
            hint="留空则自动命名",
        )
        self.si_entry.bind("<Return>", self.start_generate)

        ttk.Label(
            form,
            textvariable=self.output_hint_var,
            style="Hint.TLabel",
        ).grid(row=5, column=1, columnspan=2, sticky="w", pady=(5, 0))

        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=(12, 8))

        self.generate_btn = tk.Button(
            actions,
            text="生成文件清单  (F5)",
            command=self.start_generate,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_HOVER,
            activeforeground="white",
            disabledforeground="#dbe5f1",
            relief="flat",
            bd=0,
            padx=20,
            pady=8,
            font=(self.ui_font, 10, "bold"),
            cursor="hand2",
        )
        self.generate_btn.pack(side="left")
        self.generate_btn.bind("<Enter>", self._on_generate_enter)
        self.generate_btn.bind("<Leave>", self._on_generate_leave)

        self.open_dir_btn = ttk.Button(
            actions,
            text="打开输出目录",
            command=self.open_output_dir,
            state="disabled",
        )
        self.open_dir_btn.pack(side="left", padx=(10, 0))

        self.open_file_btn = ttk.Button(
            actions,
            text="打开清单文件",
            command=self.open_output_file,
            state="disabled",
        )
        self.open_file_btn.pack(side="left", padx=(8, 0))

        ttk.Button(actions, text="清空日志", command=self.clear_log).pack(side="left", padx=(8, 0))

        ttk.Button(actions, text="帮助 (F1)", command=self.open_help).pack(
            side="left", padx=(8, 0)
        )

        ttk.Checkbutton(
            actions,
            text="完成后自动打开输出目录",
            variable=self.auto_open_var,
            command=self._save_settings,
        ).pack(side="right")

        log_frame = ttk.LabelFrame(main, text=" 运行日志 ", padding=(8, 7))
        log_frame.pack(fill="both", expand=True)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=10,
            wrap="word",
            bg=LOG_BG,
            fg=LOG_FG,
            insertbackground="white",
            selectbackground="#264f78",
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
            font=(self.mono_font, 9),
            state="disabled",
        )
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.log_text.tag_configure("info", foreground=LOG_FG)
        self.log_text.tag_configure("success", foreground=LOG_SUCCESS)
        self.log_text.tag_configure("warn", foreground=LOG_WARN)
        self.log_text.tag_configure("error", foreground=LOG_ERROR)
        self.log_text.tag_configure("path", foreground=LOG_PATH)
        self.log_text.tag_configure("muted", foreground=LOG_MUTED)

        self._refresh_output_hint()

    def _add_form_row(
        self,
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        widget: tk.Widget,
        button_text: str | None = None,
        button_command=None,
        hint: str | None = None,
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row, column=0, sticky="w", padx=(0, 12), pady=5
        )
        widget.grid(row=row, column=1, sticky="ew", pady=5)

        if button_text is not None:
            ttk.Button(parent, text=button_text, width=8, command=button_command).grid(
                row=row, column=2, sticky="w", padx=(8, 0), pady=5
            )
        elif hint is not None:
            ttk.Label(parent, text=hint, style="Hint.TLabel").grid(
                row=row, column=2, sticky="w", padx=(8, 0), pady=5
            )

    def _on_generate_enter(self, _event=None) -> None:
        if not self._busy:
            self.generate_btn.configure(bg=ACCENT_HOVER)

    def _on_generate_leave(self, _event=None) -> None:
        if not self._busy:
            self.generate_btn.configure(bg=ACCENT)

    # --------------------------------------------------------------- paths

    def _trunk_path(self) -> str:
        trunk = self.trunk_var.get().strip()
        return os.path.abspath(trunk) if trunk else ""

    def _project_path(self) -> str:
        project = self.project_var.get().strip()
        if not project:
            return ""
        if os.path.isabs(project):
            return os.path.abspath(project)
        trunk = self._trunk_path()
        return os.path.abspath(os.path.join(trunk, project)) if trunk else ""

    def _source_path(self) -> str:
        source = self.source_var.get().strip() or "CtrlSW"
        if os.path.isabs(source):
            return os.path.abspath(source)
        trunk = self._trunk_path()
        return os.path.abspath(os.path.join(trunk, source)) if trunk else ""

    def _default_trunk(self) -> str:
        for candidate in (app_dir(), os.getcwd()):
            try:
                with os.scandir(candidate) as entries:
                    if any(
                        entry.is_dir() and entry.name.lower().startswith("prj_")
                        for entry in entries
                    ):
                        return candidate
            except OSError:
                continue
        return app_dir()

    # ------------------------------------------------------------ settings

    def _load_settings(self) -> None:
        data: dict = {}
        try:
            with open(settings_path(), "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            data = {}

        trunk = str(data.get("trunk") or "").strip()
        if not trunk or not os.path.isdir(trunk):
            trunk = self._default_trunk()

        self.trunk_var.set(trunk)
        self.project_var.set(str(data.get("project") or ""))
        self.config_var.set(str(data.get("config") or "Debug"))
        self.source_var.set(str(data.get("source_root") or "CtrlSW"))
        self.si_name_var.set(str(data.get("si_name") or ""))
        self.auto_open_var.set(bool(data.get("auto_open", False)))

        project = self.project_var.get().strip()
        if project and not os.path.isdir(self._project_path()):
            self.project_var.set("")
            project = ""

        self._auto_si_value = default_si_name(project) if project else ""
        self._refresh_output_hint()

    def _save_settings(self, _event=None) -> None:
        data = {
            "trunk": self.trunk_var.get().strip(),
            "project": self.project_var.get().strip(),
            "config": self.config_var.get().strip(),
            "source_root": self.source_var.get().strip(),
            "si_name": self.si_name_var.get().strip(),
            "auto_open": bool(self.auto_open_var.get()),
        }
        path = settings_path()
        temp_path = path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
        except OSError:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass

    # ------------------------------------------------------------ combobox

    def refresh_projects(self) -> None:
        trunk = self.trunk_var.get().strip()
        values = list_projects(trunk)
        self.project_combo["values"] = values

        current = self.project_var.get().strip()
        if not current and values:
            self.project_var.set(values[0])

    def refresh_configs(self, preferred: str | None = None, prefer_existing: bool = False) -> None:
        project_dir = self._project_path()
        actual = find_build_configs(project_dir) if project_dir else []

        values = list(actual)
        for name in ("Debug", "Release"):
            if name not in values:
                values.append(name)
        self.config_combo["values"] = values

        current = preferred or self.config_var.get().strip()
        if current not in values or (prefer_existing and actual and current not in actual):
            if "Debug" in actual:
                current = "Debug"
            elif actual:
                current = actual[0]
            else:
                current = "Debug"
            self.config_var.set(current)

    def _on_trunk_focus_out(self, _event=None) -> None:
        trunk = self.trunk_var.get().strip()
        if trunk and not os.path.isdir(trunk):
            return
        self.refresh_projects()
        self.refresh_configs()

    def on_project_changed(self, _event=None) -> None:
        project = self.project_var.get().strip()
        auto_name = default_si_name(project) if project else ""
        current = self.si_name_var.get().strip()

        if not current or current == self._auto_si_value:
            self.si_name_var.set(auto_name)
        self._auto_si_value = auto_name

        self.refresh_configs(prefer_existing=True)
        self._refresh_output_hint()

    def _refresh_output_hint(self, *_args) -> None:
        name = self.si_name_var.get().strip() or "<自动>"
        self.output_hint_var.set(f"输出文件：{name}_filelist.txt（保存在工作区根目录）")

    # -------------------------------------------------------------- browse

    def browse_trunk(self) -> None:
        initial = self._trunk_path() or app_dir()
        chosen = filedialog.askdirectory(
            title="选择工作区（包含 Xilinx 工程和源码根目录）",
            initialdir=initial,
            mustexist=True,
        )
        if not chosen:
            return
        self.trunk_var.set(os.path.normpath(chosen))
        self.refresh_projects()
        self.on_project_changed()
        self.log(f"工作区：{self.trunk_var.get()}", "path")

    def browse_project(self) -> None:
        initial = self._project_path() or self._trunk_path() or app_dir()
        chosen = filedialog.askdirectory(
            title="选择 Xilinx 工程目录",
            initialdir=initial,
            mustexist=True,
        )
        if not chosen:
            return

        chosen = os.path.normpath(chosen)
        trunk = self._trunk_path()
        if trunk and os.path.isdir(trunk) and is_inside(chosen, trunk):
            self.project_var.set(os.path.relpath(chosen, trunk))
        else:
            self.trunk_var.set(os.path.dirname(chosen))
            self.project_var.set(os.path.basename(chosen))

        self.refresh_projects()
        self.on_project_changed()
        self.log(f"Xilinx 工程：{self._project_path()}", "path")

    def browse_source_root(self) -> None:
        initial = self._source_path() or self._trunk_path() or app_dir()
        if not os.path.isdir(initial):
            initial = self._trunk_path() or app_dir()

        chosen = filedialog.askdirectory(
            title="选择 Source Insight 源码根目录",
            initialdir=initial,
            mustexist=True,
        )
        if not chosen:
            return

        chosen = os.path.normpath(chosen)
        trunk = self._trunk_path()
        if trunk and os.path.isdir(trunk) and is_inside(chosen, trunk):
            self.source_var.set(os.path.relpath(chosen, trunk))
        else:
            self.source_var.set(chosen)
        self.log(f"源码根目录：{self._source_path()}", "path")

    # ------------------------------------------------------------ generate

    def _collect_params(self) -> dict[str, str]:
        trunk = self._trunk_path()
        if not trunk or not os.path.isdir(trunk):
            raise SIError("请选择有效的工作区目录。")

        project = self.project_var.get().strip()
        if not project:
            raise SIError("请选择或输入 Xilinx 工程。")
        project_dir = self._project_path()
        if not os.path.isdir(project_dir):
            raise SIError(f"工程目录不存在：\n{project_dir}")

        config = self.config_var.get().strip() or "Debug"
        build_dir = os.path.join(project_dir, config)
        if not os.path.isdir(build_dir):
            raise SIError(
                f"构建目录不存在：\n{build_dir}\n\n"
                f"请先使用 {config} 配置完整编译一次工程。"
            )

        source_dir = self._source_path()
        if not source_dir or not os.path.isdir(source_dir):
            raise SIError(f"源码根目录不存在：\n{source_dir}")

        si_name = self.si_name_var.get().strip() or default_si_name(project)

        return {
            "trunk": trunk,
            "project": project,
            "config": config,
            "source": self.source_var.get().strip() or "CtrlSW",
            "si_name": si_name,
        }

    def start_generate(self, _event=None) -> None:
        if self._busy:
            return

        try:
            params = self._collect_params()
        except SIError as exc:
            self.log(str(exc), "error")
            messagebox.showerror("参数错误", str(exc), parent=self)
            return

        self._busy = True
        self._start_time = time.perf_counter()
        self._queue = queue.Queue()

        self.generate_btn.configure(
            state="disabled", text="正在生成…", bg=ACCENT_DISABLED, cursor="arrow"
        )
        self.open_dir_btn.configure(state="disabled")
        self.open_file_btn.configure(state="disabled")
        self.progress.pack(side="right")
        self.progress.start(12)
        self.status_var.set("正在分析构建产物…")

        self.log("开始生成文件清单…", "info")
        self.log(f"工程：{params['project']}    配置：{params['config']}", "muted")

        worker = threading.Thread(target=self._worker, args=(params,), daemon=True)
        worker.start()
        self.after(80, self._poll_queue)

    def _worker(self, params: dict[str, str]) -> None:
        try:
            result = generate_filelist(
                trunk_dir=params["trunk"],
                project_folder=params["project"],
                source_root=params["source"],
                config=params["config"],
                si_project_name=params["si_name"],
                logger=lambda message, level="info": self._queue.put(
                    ("log", message, level)
                ),
            )
            self._queue.put(("done", result))
        except SIError as exc:
            self._queue.put(("error", str(exc)))
        except Exception:
            self._queue.put(("error", "发生未预期错误：\n\n" + traceback.format_exc()))

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.log(item[1], item[2])
                elif kind == "done":
                    self._on_done(item[1])
                    return
                elif kind == "error":
                    self._on_error(item[1])
                    return
        except queue.Empty:
            pass

        if self._busy:
            self.after(80, self._poll_queue)

    def _on_done(self, result: GenerateResult) -> None:
        self._busy = False
        elapsed = time.perf_counter() - self._start_time
        self.progress.stop()
        self.progress.pack_forget()
        self._reset_generate_button()

        self._last_result = result
        self.open_dir_btn.configure(state="normal")
        self.open_file_btn.configure(state="normal")
        self.status_var.set(
            f"完成：{result.listed_count} 个文件，用时 {elapsed:.1f} s"
        )

        for warning in result.warnings:
            self.log("提示：" + warning, "warn")

        self.log(
            f"完成：源文件 {result.source_count}，头文件 {result.header_count}，"
            f"纳入清单 {result.listed_count}，清单外 {result.outside_count}",
            "success",
        )

        self._save_settings()

        if self.auto_open_var.get():
            self.open_output_dir(silent=True)

    def _on_error(self, message: str) -> None:
        self._busy = False
        self.progress.stop()
        self.progress.pack_forget()
        self._reset_generate_button()
        self.status_var.set("生成失败")
        self.log(str(message), "error")
        messagebox.showerror("生成失败", str(message)[:2000], parent=self)

    def _reset_generate_button(self) -> None:
        self.generate_btn.configure(
            state="normal",
            text="生成文件清单  (F5)",
            bg=ACCENT,
            cursor="hand2",
        )

    def open_output_dir(self, silent: bool = False) -> None:
        target = ""
        if self._last_result is not None:
            target = os.path.dirname(self._last_result.output_file)
        if not target:
            target = self._trunk_path()

        if not target or not os.path.isdir(target):
            if not silent:
                messagebox.showwarning("打开目录", "输出目录不存在。", parent=self)
            return

        try:
            os.startfile(target)
        except OSError as exc:
            if not silent:
                messagebox.showerror("打开目录", f"无法打开目录：\n{exc}", parent=self)

    def open_output_file(self) -> None:
        if self._last_result is None or not os.path.isfile(self._last_result.output_file):
            messagebox.showwarning("打开文件", "尚未生成清单文件。", parent=self)
            return

        try:
            os.startfile(self._last_result.output_file)
        except OSError as exc:
            messagebox.showerror("打开文件", f"无法打开文件：\n{exc}", parent=self)

    def open_help(self, _event=None) -> None:
        try:
            target = prepare_help_file()
        except SIError as exc:
            messagebox.showwarning("帮助", str(exc), parent=self)
            return

        try:
            os.startfile(target)
        except OSError as exc:
            messagebox.showerror(
                "帮助",
                f"无法打开使用教程：\n{exc}\n\n教程位置：\n{target}",
                parent=self,
            )

    # ----------------------------------------------------------------- log

    def log(self, message: str, level: str = "info") -> None:
        if level not in {"info", "success", "warn", "error", "path", "muted"}:
            level = "info"

        timestamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] ", "muted")
        self.log_text.insert("end", str(message).rstrip() + "\n", level)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # --------------------------------------------------------------- misc

    def apply_cli_args(self, args: list[str]) -> bool:
        if not args:
            return False

        project = args[0].strip()
        if not project:
            return False

        if os.path.isabs(project):
            project = os.path.normpath(project)
            self.trunk_var.set(os.path.dirname(project))
            self.project_var.set(os.path.basename(project))
        else:
            self.project_var.set(project)
            trunk = self._trunk_path()
            if not trunk or not os.path.isdir(os.path.join(trunk, project)):
                self.trunk_var.set(app_dir())

        self.source_var.set(args[1].strip() if len(args) >= 2 and args[1].strip() else "CtrlSW")
        if len(args) >= 3 and args[2].strip():
            self.si_name_var.set(args[2].strip())
        else:
            self.si_name_var.set(default_si_name(project))

        config_given = len(args) >= 4 and bool(args[3].strip())
        self.config_var.set(args[3].strip() if config_given else "Debug")

        self._auto_si_value = default_si_name(project)
        self.refresh_projects()
        self.refresh_configs(prefer_existing=not config_given)
        self._refresh_output_hint()

        self.clear_log()
        self.log(f"欢迎使用 {APP_NAME} v{APP_VERSION}", "success")
        self.log("请先完整编译一次 Xilinx 工程，再点击“生成文件清单”。", "muted")
        self.log(f"命令行参数：{' '.join(args)}", "muted")
        self.log(f"工作区：{self._trunk_path()}", "path")
        self.log(f"输出目录：{self._trunk_path()}", "path")
        return True

    def _on_close(self) -> None:
        if self._busy:
            if not messagebox.askyesno(
                "退出", "正在生成文件清单，确定要退出吗？", parent=self
            ):
                return
        self._save_settings()
        self.destroy()


def main() -> None:
    enable_dpi_awareness()

    raw_args = sys.argv[1:]
    if "--check-help" in raw_args:
        try:
            target = prepare_help_file()
        except SIError:
            sys.exit(2)
        sys.exit(0 if os.path.isfile(target) else 2)

    smoke_test = "--smoke-test" in raw_args
    args = [arg for arg in raw_args if not arg.startswith("--")]

    app = App()

    if smoke_test:
        app.after(1400, app.destroy)
    else:
        cli_used = app.apply_cli_args(args)
        if cli_used:
            app.after(700, app.start_generate)

    app.mainloop()


if __name__ == "__main__":
    main()
