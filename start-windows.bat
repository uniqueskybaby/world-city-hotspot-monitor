@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

echo 正在启动 世界城招商热点监测...
set "LOG_FILE=%CD%\startup-log.txt"
echo 世界城招商热点监测启动日志 > "%LOG_FILE%"
echo 当前目录：%CD% >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

call :find_python
if not defined PYTHON_CMD (
  call :install_python
  call :find_python
)

if not defined PYTHON_CMD (
  echo 未找到可用的 Python 3.9-3.13。
  echo 未找到可用的 Python 3.9-3.13。>> "%LOG_FILE%"
  start "" "https://www.python.org/downloads/windows/"
  goto fail
)

echo 使用 Python：%PYTHON_CMD%
echo 使用 Python：%PYTHON_CMD% >> "%LOG_FILE%"
%PYTHON_CMD% "%CD%\scripts\local_launcher.py"
if %ERRORLEVEL% NEQ 0 goto fail
exit /b 0

:find_python
set "PYTHON_CMD="
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  for %%V in (3.12 3.11 3.10 3.9 3.13) do (
    py -%%V -c "import sys; raise SystemExit(0 if (3, 9) <= sys.version_info[:2] < (3, 14) else 1)" >nul 2>nul
    if !ERRORLEVEL! EQU 0 (
      set "PYTHON_CMD=py -%%V"
      exit /b 0
    )
  )
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  python -c "import sys; raise SystemExit(0 if (3, 9) <= sys.version_info[:2] < (3, 14) else 1)" >nul 2>nul
  if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=python"
    exit /b 0
  )
)

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
  set "PYTHON_CMD="%LocalAppData%\Programs\Python\Python312\python.exe""
  exit /b 0
)

if exist "%ProgramFiles%\Python312\python.exe" (
  set "PYTHON_CMD="%ProgramFiles%\Python312\python.exe""
  exit /b 0
)

exit /b 0

:install_python
echo 未检测到兼容的 Python 3.9-3.13，正在尝试自动安装 Python 3.12...
echo 未检测到兼容的 Python 3.9-3.13，正在尝试自动安装 Python 3.12。>> "%LOG_FILE%"
where winget >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  echo 当前 Windows 未找到 winget，无法自动安装 Python。
  echo 请在打开的页面安装 Python 3.12，并勾选 Add python.exe to PATH。
  echo 未找到 winget。>> "%LOG_FILE%"
  start "" "https://www.python.org/downloads/windows/"
  exit /b 1
)

winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements >> "%LOG_FILE%" 2>&1
if %ERRORLEVEL% NEQ 0 (
  echo Python 自动安装失败，请查看 startup-log.txt。
  exit /b 1
)
exit /b 0

:fail
echo.
echo 启动失败。请把当前文件夹里的 startup-log.txt 发给项目维护方定位。
pause
exit /b 1
