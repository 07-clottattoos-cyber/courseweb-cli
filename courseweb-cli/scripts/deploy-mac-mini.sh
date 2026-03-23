#!/usr/bin/env bash
set -euo pipefail

REMOTE_HOST="${1:-1cxm1@1cxm1demac-mini.local}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${SCRIPT_DIR}/deploy-remote.sh" "${REMOTE_HOST}" "${PKUCW_REMOTE_DIR:-pkucw-cli}"
