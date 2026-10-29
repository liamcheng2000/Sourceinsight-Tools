@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   Build Source Insight File List Generator
echo ============================================================
echo.

echo [1/2] Building offline help page...
python build_help.py
if errorlevel 1 (
    echo.
    echo Help build FAILED. Install the Markdown package:
    echo   python -m pip install markdown
    exit /b 1
)

echo.
echo [2/2] Packaging exe...
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name SI_FileList_Generator ^
  --icon "app.ico" ^
  --add-data "app.ico;." ^
  --add-data "help.html;." ^
  --version-file "version_info.txt" ^
  si_filelist_gui.py

if errorlevel 1 (
    echo.
    echo Build FAILED.
    exit /b 1
)

echo.
echo Build OK.
echo   dist\SI_FileList_Generator.exe
echo.
echo The exe is standalone and can be renamed or moved freely.
exit /b 0
