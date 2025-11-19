#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
VENV_PATH="${PROJECT_ROOT}/.venv"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 is required to bootstrap the environment" >&2
  exit 1
fi

if [ ! -d "${VENV_PATH}" ]; then
  echo "[INFO] Creating virtual environment at ${VENV_PATH}" >&2
  python3 -m venv "${VENV_PATH}"
fi

# shellcheck disable=SC1090
source "${VENV_PATH}/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r "${PROJECT_ROOT}/requirements.txt"

echo "[INFO] Python dependencies installed into ${VENV_PATH}" >&2

if ! command -v surelog >/dev/null 2>&1; then
  cat >&2 <<'MSG'
[WARN] Surelog binary not found in PATH.
       Install Surelog (https://github.com/chipsalliance/Surelog) and ensure the
       'surelog' executable is discoverable so the UHDM frontend can run.
MSG
else
  echo "[INFO] Found surelog at $(command -v surelog)" >&2
fi

check_uhdm_import() {
python <<'PY'
import sys
try:
    from rtl_fingerprint.uhdm_compat import get_uhdm
    get_uhdm()
except Exception as exc:
    print("[WARN] Unable to import 'uhdm':", exc, file=sys.stderr)
    print("       Build Surelog with -DSURELOG_WITH_PYTHON=ON or provide", file=sys.stderr)
    print("       the bindings via PYTHONPATH.", file=sys.stderr)
    sys.exit(1)
else:
    print("[INFO] UHDM Python bindings are importable.")
PY
}

if ! check_uhdm_import; then
  echo "[INFO] Attempting to install the prebuilt 'uhdm' wheel from PyPI" >&2
  python -m pip install uhdm
  check_uhdm_import
fi

validate_uhdm_database() {
  local db_path="$1"
  if [ ! -f "$db_path" ]; then
    return 1
  fi

  echo "[INFO] Validating UHDM database at ${db_path}" >&2
  UHDM_DB_VERIFY="$db_path" python <<'PY'
import os
from pathlib import Path
from rtl_fingerprint.uhdm_compat import get_uhdm

uhdm, _ = get_uhdm()

db_path = Path(os.environ["UHDM_DB_VERIFY"])
serializer = uhdm.Serializer()
designs = serializer.Restore(str(db_path))
if not designs:
    raise SystemExit(
        f"[ERROR] Serializer.Restore() returned no designs for {db_path}"
    )
print(f"[INFO] Successfully restored {db_path}")
PY
}

UHDM_DB_CANDIDATE="${UHDM_DB_UNDER_TEST:-}"
if [ -z "$UHDM_DB_CANDIDATE" ]; then
  for candidate in "${PROJECT_ROOT}/slpp_dir/surelog.uhdm" \
                   "${PROJECT_ROOT}/slpp_all/surelog.uhdm"; do
    if [ -f "$candidate" ]; then
      UHDM_DB_CANDIDATE="$candidate"
      break
    fi
  done
else
  if [ ! -f "$UHDM_DB_CANDIDATE" ]; then
    echo "[WARN] UHDM_DB_UNDER_TEST points to missing file: ${UHDM_DB_CANDIDATE}" >&2
    UHDM_DB_CANDIDATE=""
  fi
fi

if [ -n "$UHDM_DB_CANDIDATE" ]; then
  validate_uhdm_database "$UHDM_DB_CANDIDATE"
else
  echo "[INFO] No slpp_dir/surelog.uhdm database detected for validation" >&2
fi
