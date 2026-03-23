#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${1:-1cxm1@1cxm1demac-mini.local}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_DIR="${COURSEWEB_REMOTE_DIR:-courseweb-cli}"

tar \
  --exclude='.DS_Store' \
  --exclude='output' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  -czf - -C "${PROJECT_DIR}" . \
| ssh "${REMOTE_HOST}" "\
  rm -rf ~/${REMOTE_DIR} && \
  mkdir -p ~/${REMOTE_DIR} && \
  tar xzf - -C ~/${REMOTE_DIR} && \
  cd ~/${REMOTE_DIR} && \
  chmod +x ./install.sh ./scripts/deploy-mac-mini.sh && \
  ./install.sh"

ssh "${REMOTE_HOST}" "cd ~/${REMOTE_DIR} && chmod +x ./scripts/smoke-test.sh && ./scripts/smoke-test.sh"
