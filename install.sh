#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="${COURSEWEB_INSTALL_ROOT:-$HOME/.local/share/courseweb-cli}"
BIN_DIR="${COURSEWEB_BIN_DIR:-$HOME/.local/bin}"
PATH_EXPORT_LINE="export PATH=\"${BIN_DIR}:\$PATH\""

pick_python() {
  if [[ -n "${COURSEWEB_PYTHON:-}" ]]; then
    printf '%s\n' "${COURSEWEB_PYTHON}"
    return 0
  fi

  local candidate
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  return 1
}

python_is_supported() {
  local candidate="$1"
  "${candidate}" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

install_uv_python() {
  local uv_bin="${HOME}/.local/bin/uv"
  if [[ ! -x "${uv_bin}" ]]; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  export PATH="${HOME}/.local/bin:${PATH}"
  "${uv_bin}" python install 3.12
  "${uv_bin}" python find 3.12
}

pick_profile_file() {
  local shell_name
  shell_name="$(basename "${SHELL:-}")"

  case "${shell_name}" in
    zsh)
      printf '%s\n' "${HOME}/.zprofile"
      ;;
    bash)
      printf '%s\n' "${HOME}/.bash_profile"
      ;;
    *)
      printf '%s\n' "${HOME}/.profile"
      ;;
  esac
}

ensure_path_config() {
  local profile_file="$1"
  mkdir -p "$(dirname "${profile_file}")"
  touch "${profile_file}"
  if ! grep -F "${PATH_EXPORT_LINE}" "${profile_file}" >/dev/null 2>&1; then
    {
      echo
      echo "# Added by courseweb-cli installer"
      echo "${PATH_EXPORT_LINE}"
    } >> "${profile_file}"
    printf '%s\n' "${profile_file}"
    return 0
  fi

  return 1
}

PYTHON_BIN="$(pick_python || true)"
if [[ -z "${PYTHON_BIN}" ]] || ! python_is_supported "${PYTHON_BIN}"; then
  echo "Python 3.10+ was not found on PATH. Installing a user-local Python with uv..." >&2
  PYTHON_BIN="$(install_uv_python)"
fi

"${PYTHON_BIN}" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("courseweb-cli needs Python 3.10 or newer")
PY

VENV_DIR="${INSTALL_ROOT}/.venv"
mkdir -p "${INSTALL_ROOT}" "${BIN_DIR}" "${HOME}/.courseweb"

"${PYTHON_BIN}" -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel
"${VENV_DIR}/bin/pip" install -e "${PROJECT_DIR}"
"${VENV_DIR}/bin/python" -m playwright install chromium

ln -sf "${VENV_DIR}/bin/courseweb" "${BIN_DIR}/courseweb"
ln -sf "${VENV_DIR}/bin/cw" "${BIN_DIR}/cw"
export PATH="${BIN_DIR}:${PATH}"

PROFILE_FILE="$(pick_profile_file)"
UPDATED_PROFILE=""
if UPDATED_PROFILE="$(ensure_path_config "${PROFILE_FILE}")"; then
  PROFILE_NOTE="Updated ${UPDATED_PROFILE} so future shells can find cw."
else
  PROFILE_NOTE="PATH already includes ${BIN_DIR} in ${PROFILE_FILE}."
fi

echo
echo "Installed courseweb-cli."
echo "  Python: ${PYTHON_BIN}"
echo "  Venv:   ${VENV_DIR}"
echo "  Bins:   ${BIN_DIR}/courseweb, ${BIN_DIR}/cw"
echo "  Shell:  ${PROFILE_NOTE}"

case ":$PATH:" in
  *":${BIN_DIR}:"*) ;;
  *)
    echo
    echo "Add this to your shell profile if needed:"
    echo "  export PATH=\"${BIN_DIR}:\$PATH\""
    ;;
esac

echo
"${BIN_DIR}/cw" doctor
