#!/usr/bin/env bash
set -euo pipefail

export PATH="${HOME}/.local/bin:${PATH}"
COURSEWEB_BIN="${COURSEWEB_BIN:-cw}"

run() {
  echo
  echo "+ $*"
  "$@"
}

run "${COURSEWEB_BIN}" --version
run "${COURSEWEB_BIN}" doctor --json
run "${COURSEWEB_BIN}" --help >/dev/null
run "${COURSEWEB_BIN}" recordings --help >/dev/null
