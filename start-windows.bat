@echo off
setlocal
cd /d "%~dp0"

echo 正在启动 世界城招商热点监测...

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set PYTHON=py -3
) else (
  set PYTHON=python
)

%PYTHON% --version >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  echo 未找到 Python 3，请先安装 Python 3。
  pause
  exit /b 1
)

where npm >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  echo 未找到 Node.js / npm，请先安装 Node.js。
  pause
  exit /b 1
)

if not exist ".venv" (
  %PYTHON% -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
npm install
npm run build

set DATA_DIR=data
set USE_SAMPLE_DATA=true
start "" "http://127.0.0.1:8000"
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
pause
