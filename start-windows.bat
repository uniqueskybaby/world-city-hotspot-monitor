@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo 正在启动 世界城招商热点监测...
set "LOG_FILE=%CD%\startup-log.txt"
echo 世界城招商热点监测启动日志 > "%LOG_FILE%"
echo 当前目录：%CD% >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set "PYTHON=py -3"
) else (
  set "PYTHON=python"
)

%PYTHON% --version >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  echo 未找到 Python 3，请先安装 Python 3。
  echo 下载地址：https://www.python.org/downloads/windows/
  echo 未找到 Python 3。>> "%LOG_FILE%"
  pause
  exit /b 1
)

%PYTHON% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >> "%LOG_FILE%" 2>&1
if %ERRORLEVEL% NEQ 0 (
  echo 当前 Python 版本过低，请安装 Python 3.9 或更高版本。
  echo 当前 Python 版本过低。>> "%LOG_FILE%"
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  call :run "创建 Python 运行环境" "%PYTHON% -m venv .venv" || goto fail
)

call .venv\Scripts\activate.bat >> "%LOG_FILE%" 2>&1
if %ERRORLEVEL% NEQ 0 (
  echo Python 运行环境启动失败，请查看 startup-log.txt。
  goto fail
)

call :run "升级 pip" "python -m pip install --upgrade pip" || goto fail
call :run "安装后端依赖" "python -m pip install -r requirements.txt" || goto fail

if exist "dist\index.html" (
  echo 已检测到内置页面文件，跳过 Node.js 前端构建。
  echo 已检测到 dist\index.html，跳过 Node.js 前端构建。>> "%LOG_FILE%"
) else (
  where node >nul 2>nul
  if %ERRORLEVEL% NEQ 0 (
    echo 未找到 Node.js。当前包缺少 dist 页面文件时，需要安装 Node.js 22 LTS。
    echo 下载地址：https://nodejs.org/
    echo 未找到 Node.js。>> "%LOG_FILE%"
    pause
    exit /b 1
  )
  where npm >nul 2>nul
  if %ERRORLEVEL% NEQ 0 (
    echo 未找到 npm，请重新安装 Node.js 22 LTS。
    echo 未找到 npm。>> "%LOG_FILE%"
    pause
    exit /b 1
  )
  node -e "const [major, minor] = process.versions.node.split('.').map(Number); process.exit((major === 20 && minor >= 19) || (major === 22 && minor >= 12) || major > 22 ? 0 : 1)" >> "%LOG_FILE%" 2>&1
  if %ERRORLEVEL% NEQ 0 (
    echo Node.js 版本过低，请安装 Node.js 20.19+ 或 22.12+。
    echo Node.js 版本过低。>> "%LOG_FILE%"
    pause
    exit /b 1
  )
  call :run "安装前端依赖" "npm install" || goto fail
  call :run "构建前端页面" "npm run build" || goto fail
)

set DATA_DIR=data
set USE_SAMPLE_DATA=true
start "" cmd /c "timeout /t 3 >nul && start http://127.0.0.1:8000"
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
if %ERRORLEVEL% NEQ 0 goto fail
pause
exit /b 0

:run
set "STEP=%~1"
set "COMMAND=%~2"
echo %STEP%...
echo [%STEP%] %COMMAND% >> "%LOG_FILE%"
cmd /c "%COMMAND%" >> "%LOG_FILE%" 2>&1
if %ERRORLEVEL% NEQ 0 (
  echo %STEP% 失败，请查看 startup-log.txt。
  echo [%STEP%] 失败。>> "%LOG_FILE%"
  exit /b 1
)
echo [%STEP%] 完成。>> "%LOG_FILE%"
exit /b 0

:fail
echo.
echo 启动失败。请把当前文件夹里的 startup-log.txt 发给项目维护方定位。
pause
exit /b 1
