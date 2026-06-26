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

python3 scripts/local_launcher.py
