# Source Insight 文件清单生成器

一个带图形界面的 Windows 小工具：从 Xilinx/Vitis（Eclipse CDT）工程的**真实构建产物**中提取参与编译的源文件和头文件，生成 Source Insight 可直接导入的工程文件清单。

`SI文件清单生成器.exe` 是单文件程序，目标机器无需安装 Python。

> **下载最新版**：[GitHub Releases](https://github.com/liamcheng2000/Sourceinsight-Tools/releases)  
> **图文教程**：[`使用教程.md`](使用教程.md)  
> 程序内点击 **帮助 (F1)** 可随时打开同样的离线教程。

---

## 解决的问题

直接把整个目录树加入 Source Insight，会把大量未使用的文件、BSP 生成代码、备份文件也索引进来，导致符号跳转不准、索引变慢。

本工具只读取真实构建结果：

- 从 `Debug/**/subdir.mk` 的 `C_SRCS`、`CPP_SRCS`、`CXX_SRCS`、`ASM_SRCS` 等变量提取源文件；
- 从 GCC 生成的 `*.d` 依赖文件提取实际被包含的头文件；
- 自动去重、校验文件是否存在、按源码根目录过滤；
- 输出相对路径清单 `SI_xxx_filelist.txt`；
- 构建使用但位于源码根目录之外的文件，单独输出到 `SI_xxx_outside_root.txt`，便于人工确认。

---

## 快速开始

1. **先完整编译一次 Xilinx 工程**，确保构建目录中存在 `subdir.mk` 和 `*.d` 文件。
2. 从 [Releases](https://github.com/liamcheng2000/Sourceinsight-Tools/releases) 下载 `SI文件清单生成器.exe`，放到工作区根目录（推荐），也可以放到任意位置后手动选择目录。
3. 双击运行，填写参数：

   | 字段 | 说明 |
   |---|---|
   | 工作区 | 包含 `Prj_*` 工程和 `CtrlSW` 的根目录 |
   | Xilinx 工程 | 例如 `Prj_Demo`，可从下拉框选择或手动输入 |
   | 构建配置 | 通常是 `Debug`，也可以是 `Release` 或自定义配置目录名 |
   | 源码根目录 | 通常是 `CtrlSW`，即希望 Source Insight 索引的源码根 |
   | SI 工程名称 | 留空时自动生成 `SI_<去掉 Prj_ 前缀的工程名>` |

4. 点击 **“生成文件清单 (F5)”**。
5. 在 Source Insight 中导入生成的清单：
   - 打开 `Project → Add and Remove Project Files…`；
   - 点击 `Add from list…`，选择生成的 `SI_xxx_filelist.txt`；
   - 在 `Project → Project Settings…` 中确认 `Project Source Root` 与界面显示的源码根目录一致。

> 第一次使用建议先看 [`使用教程.md`](使用教程.md)。程序内的 **帮助 (F1)** 按钮会打开同一份图文教程，不需要联网。

> 不同 Source Insight 版本的菜单文字可能略有差异。清单中的路径是相对路径，必须以正确的源码根目录为基准。

---

## 命令行 / 拖拽

命令行参数与原批处理脚本保持一致：

```bat
SI文件清单生成器.exe PROJECT [SourceRoot] [SIProjectName] [Config]
```

示例：

```bat
REM 使用默认源码根 CtrlSW、自动 SI 名称、Debug 配置
SI文件清单生成器.exe Prj_Demo

REM 完整指定
SI文件清单生成器.exe Prj_Demo CtrlSW SI_Demo Debug

REM 直接传工程绝对路径（工作区自动取其父目录）
SI文件清单生成器.exe D:\work\trunk\Prj_Demo
```

- 带参数启动时，程序会打开界面并**自动开始生成**。
- 只传工程名时：源码根默认 `CtrlSW`，配置默认 `Debug`，SI 名称自动推导。
- 相对工程名优先在上次使用的工作区中查找；找不到则回退到 exe 所在目录。
- 也可以直接把**工程文件夹拖到 exe 上**，效果等同于传入工程绝对路径。

---

## 输出文件

| 文件 | 内容 |
|---|---|
| `SI_xxx_filelist.txt` | Source Insight 文件清单，UTF-8 BOM，`;` 开头为注释 |
| `SI_xxx_outside_root.txt` | 构建使用但不在源码根目录下的文件（仅当存在时生成） |

清单正文示例：

```text
; Source Insight Project File List
; Project Name: SI_Demo
; Xilinx Project: Prj_Demo
; Build Config: Debug
; Source Root: D:\work\trunk\CtrlSW
; Version=4.00.0150
;
inc\app.h
src\main.c
src\util.c
```

如果本次生成时没有清单外文件，程序会自动删除上次遗留的同名 `*_outside_root.txt`。

---

## 工作原理

```text
Debug/**/subdir.mk ──► 解析 C_SRCS / CPP_SRCS / ASM_SRCS ... ──┐
                                                               ├─► 去重 ─► 按源码根过滤 ─► *_filelist.txt
Debug/**/*.d       ──► 解析 GCC 依赖列表中的头文件 ────────────┘                        └─► *_outside_root.txt
```

实现中处理了这些细节：

- makefile 反斜杠续行；
- 路径中的转义空格（`my\ file.c`）；
- 引号、尾部反斜杠、`$(VAR)` / `${VAR}` 等无法解析的 Make 变量（跳过并记录警告）；
- Windows 盘符、正反斜杠混用；
- 大小写不敏感去重；
- 文件存在性校验（过滤构建残留中已删除的文件）。

---

## 注意事项

1. **必须先构建一次**。没有 `subdir.mk` 时会提示“请先完整编译一次工程”。
2. **头文件依赖 `.d`**。若编译器没有开启 `-MMD / -MP` 之类的依赖生成选项，只能得到源文件，头文件列表为空。
3. **BSP / 驱动头文件默认不在清单中**。它们若位于 `CtrlSW` 之外，只会出现在 `*_outside_root.txt`。如果希望一起索引，可把“源码根目录”改为更高的公共父目录，并在 Source Insight 中同步修改 Project Source Root。
4. **构建产物可能过期**。切换配置或大量增删源码后，建议重新构建再生成。
5. **首次启动稍慢**。单文件 exe 启动时需要解压运行时，通常 1～3 秒。
6. **SmartScreen / 杀毒软件**。exe 未做代码签名，Windows 可能提示“未知发布者”；这是单文件打包程序的常见现象。
7. 界面设置保存在 `%APPDATA%\SourceInsightFileList\settings.json`，不会写入 exe 所在目录。
8. **帮助按钮**点击时会把内置教程复制到 `%APPDATA%\SourceInsightFileList\使用教程.html`，然后调用系统默认浏览器。

---

## 重新构建 exe

环境要求：Windows 10/11 x64、Python 3.10+（本项目在 Python 3.14 + PyInstaller 6.21 下验证）、Tkinter。

```bat
REM 安装打包工具（只需一次）
python -m pip install pyinstaller markdown

REM 构建（会先根据 使用教程.md 生成 help.html，再打包 exe）
build_exe.bat
```

生成结果：`dist\SI_FileList_Generator.exe`。

把生成的 exe 上传到 **GitHub Releases**，不要提交到源码仓库。当前仓库保持纯源码；发布时上传单文件 exe 即可。

如需重新生成图标（需要 Pillow）：

```bat
python -m pip install pillow
python make_icon.py
```

如需单独生成网页版教程：

```bat
python build_help.py
```

会输出 `使用教程.html` 和 `help.html`（两者内容相同，图片已内嵌，可离线打开）。

---

## 文件说明

| 文件 | 说明 |
|---|---|
| `GitHub Releases` | 单文件 exe 的下载位置，不放进源码仓库 |
| `si_core.py` | 核心解析与清单生成逻辑，无 GUI 依赖 |
| `si_filelist_gui.py` | Tkinter 图形界面入口 |
| `test_si_core.py` | 核心逻辑自测（`python test_si_core.py`） |
| `build_help.py` | 把 `使用教程.md` 转换为自包含 HTML |
| `使用教程.md` | 图文使用教程源文件 |
| `使用教程.html` | 本地生成的网页版教程，不提交到仓库 |
| `help.html` | 打包进 exe 的内置教程，构建时生成，不提交到仓库 |
| `docs\images\` | 教程配图 |
| `app.ico` | 程序图标 |
| `make_icon.py` | 图标生成脚本（构建时可选） |
| `version_info.txt` | exe 版本信息资源 |
| `build_exe.bat` | 一键打包脚本 |
| `gen_sourceinsight_filelist.bat` / `.ps1` | 原始 PowerShell 版本，保留作参考 |
| `RM.txt` | 原始脚本的示例运行命令 |
