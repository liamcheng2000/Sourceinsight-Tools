@echo off
setlocal EnableExtensions

rem ============================================================
rem Generate Source Insight file list from the REAL Xilinx build.
rem
rem Usage:
rem   gen_sourceinsight_filelist.bat PROJECT [SourceRoot] [SIProjectName] [Config]
rem
rem Examples:
rem   gen_sourceinsight_filelist.bat Prj_Demo
rem   gen_sourceinsight_filelist.bat Prj_Demo CtrlSW SI_Demo
rem   gen_sourceinsight_filelist.bat Prj_Demo . SI_Demo Debug
rem
rem Defaults:
rem   SourceRoot    = CtrlSW
rem   SIProjectName = SI_<project name without Prj_>
rem   Config        = Debug
rem ============================================================

set "PROJECT=%~1"
set "SOURCE_ROOT=%~2"
set "SI_NAME=%~3"
set "CONFIG=%~4"

if not defined PROJECT (
    echo.
    echo Usage:
    echo   %~nx0 PROJECT [SourceRoot] [SIProjectName] [Config]
    echo.
    echo Example matching your Source Insight style:
    echo   %~nx0 Prj_Demo CtrlSW SI_Demo Debug
    echo.
    exit /b 1
)

if not defined SOURCE_ROOT set "SOURCE_ROOT=CtrlSW"
if not defined CONFIG set "CONFIG=Debug"

powershell.exe -NoProfile -ExecutionPolicy Bypass ^
  -File "%~dp0gen_sourceinsight_filelist.ps1" ^
  -ProjectFolder "%PROJECT%" ^
  -SourceRoot "%SOURCE_ROOT%" ^
  -SIProjectName "%SI_NAME%" ^
  -Config "%CONFIG%"

exit /b %ERRORLEVEL%
