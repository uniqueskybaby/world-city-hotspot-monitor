#!/bin/zsh
set -e

cd "$(dirname "$0")"

echo "正在启动 世界城招商热点监测..."

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3，请先安装 Python 3。"
  read "?按回车键退出。"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "未找到 Node.js / npm，请先安装 Node.js。"
  read "?按回车键退出。"
  exit 1
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
npm install
npm run build

(sleep 2 && open "http://127.0.0.1:8000") >/dev/null 2>&1 &

export DATA_DIR="${DATA_DIR:-data}"
export USE_SAMPLE_DATA="${USE_SAMPLE_DATA:-true}"
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
