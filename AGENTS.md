# AGENTS.md

## Project

Windows-only Python/Tkinter tool that converts Xilinx/Vitis Eclipse CDT build output (`subdir.mk`, `*.d`) into a Source Insight file list. It ships as a one-file exe. Verified with Python 3.14, Tk 8.6, PyInstaller 6.21. UI text and docs are Chinese; keep user-facing strings Chinese.

## Entry points

- `si_core.py` — GUI-free parser/generator. `generate_filelist()` is the API used by tests.
- `si_filelist_gui.py` — Tkinter UI and PyInstaller entrypoint. CLI: `python si_filelist_gui.py PROJECT [SourceRoot] [SIProjectName] [Config]` opens the GUI and auto-generates after 700 ms.
- `build_help.py` — renders `使用教程.md` + `docs/images/` into `使用教程.html` and `help.html` (base64 images, offline).
- `build_exe.bat` — regenerates help, then builds the one-file exe.
- `gen_sourceinsight_filelist.*` / `RM.txt` — legacy PowerShell reference; not the active implementation.

## Commands

```bat
REM no requirements.txt; install once
python -m pip install pyinstaller markdown pillow

REM canonical test suite / single test
python test_si_core.py
python test_si_core.py GenerateFilelistTests.test_generate_and_filter

REM help + GUI verification
python build_help.py
python si_filelist_gui.py --smoke-test
python si_filelist_gui.py --check-help

REM build
build_exe.bat
```

- `--smoke-test` opens a real Tk window and exits after ~1.4 s; it needs a desktop session.
- `--check-help` creates no window, requires `help.html` in source runs (run `python build_help.py` first), and exits `0`/`2`.
- No CI, linter, formatter, or typecheck config exists. The test suite, smoke test, help check, and build are the verification path.

## Non-obvious behavior

- Every path token in any `subdir.mk` or `*.d` is resolved relative to the **build-config directory** (for example `Prj_Demo/Debug`), not relative to the makefile's own directory. The tests encode this; preserve it.
- Main-list paths are relative to `source_root`. Files outside it go to `<SI>_outside_root.txt` and never enter the main list. A stale outside file is deleted when none remain.
- Output must stay UTF-8 BOM + CRLF, with backslash-separated relative paths and `;` comments, for Source Insight compatibility.
- Only `C_SRCS`, `CPP_SRCS`, `CXX_SRCS`, `CC_SRCS`, `ASM_SRCS`, and `S_UPPER_SRCS` are parsed. `$(...)` paths are skipped with a warning; escaped spaces are supported.
- `default_si_name()` strips a `Prj_` prefix and prepends `SI_`; invalid filename characters are rejected.
- `CtrlSW` (source root) and `Debug` (config) are intentional runtime defaults. Do not rename them just to make examples generic.

## Docs and release

- Edit `使用教程.md` and `docs/images/`, never the generated `help.html` / `使用教程.html`; run `build_help.py` or `build_exe.bat` to rebuild.
- `docs/make_images.py` needs Pillow, Windows fonts, and untracked raw screenshots. Its annotation rows assume 125% DPI (`1242x996`); recapture raws before rerunning.
- Keep versions in sync in `si_core.APP_VERSION`, `build_help.py` (`version = ...`), and `version_info.txt`. Update `README.md` and `使用教程.md` when CLI behavior changes.

## Repo hygiene

- This is a public repository. Examples must remain generic (`Prj_Demo`, `SI_Demo`); do not add real customer/project names or personal paths.
- Keep the repo-local commit identity `LIAM <349333949+liamcheng2000@users.noreply.github.com>`; do not commit with a personal email or machine name.
- Never commit `SI文件清单生成器.exe`, `help.html`, `使用教程.html`, `build/`, `dist/`, `*.spec`, or `__pycache__`; `.gitignore` covers them. Publish the exe through GitHub Releases.
- GUI state lives in `%APPDATA%\SourceInsightFileList\settings.json`; the help copy is `%APPDATA%\SourceInsightFileList\使用教程.html`. Delete them to reset local state.
