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

python3 scripts/local_launcher.py
