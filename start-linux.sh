#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Starting 世界城招商热点监测..."

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js and npm are required."
  exit 1
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ -f "dist/index.html" ]; then
  echo "Built frontend found; skipping frontend build."
else
  if ! command -v npm >/dev/null 2>&1; then
    echo "Node.js and npm are required when dist/index.html is missing."
    exit 1
  fi
  npm install
  npm run build
fi

if command -v xdg-open >/dev/null 2>&1; then
  (sleep 2 && xdg-open "http://127.0.0.1:8000") >/dev/null 2>&1 &
fi

export DATA_DIR="${DATA_DIR:-data}"
export USE_SAMPLE_DATA="${USE_SAMPLE_DATA:-true}"
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
