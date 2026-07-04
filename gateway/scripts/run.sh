#!/usr/bin/env bash
# 本地一键：建 venv + 起 gateway + 健康检查。
# 在 atelier 仓库根目录运行。

set -euo pipefail

cd "$(dirname "$0")/../gateway/api" || exit 1

if [ ! -d ".venv" ]; then
  echo ">> creating venv ..."
  python3 -m venv .venv
fi
source .venv/bin/activate

echo ">> installing ..."
pip install -e .

: "${GATEWAY_AUTH_TOKEN:=dev-$(openssl rand -hex 8)}"
export GATEWAY_AUTH_TOKEN

echo ">> starting gateway on :8080 (token=${GATEWAY_AUTH_TOKEN}) ..."
exec uvicorn main:app --reload --host 0.0.0.0 --port 8080
