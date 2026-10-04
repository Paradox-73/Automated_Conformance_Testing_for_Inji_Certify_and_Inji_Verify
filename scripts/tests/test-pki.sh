#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# Runs the unit tests of compose/pki/generate.py (Python standard library plus the openssl command).
#
#   bash scripts/tests/test-pki.sh
#
# "bash scripts/check.sh shell" runs this file. Without Python 3.12+ or OpenSSL 3 it prints a skip note and exits
# 0 outside strict mode, and exits 1 in strict mode (CI=true or HARNESS_CHECK_STRICT=1), so CI never skips it.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
# shellcheck source=../lib/common.sh
source "$REPO/scripts/lib/common.sh"

skip_or_fail() {
  if [[ ${CI:-} == true || ${HARNESS_CHECK_STRICT:-0} == 1 ]]; then
    printf 'not ok - %s (strict mode)\n' "$1"
    exit 1
  fi
  printf 'ok - # SKIP %s\n' "$1"
  exit 0
}

python=$(harness_find_python) || skip_or_fail "Python 3.$HARNESS_PYTHON_MIN_MINOR or newer not found"
command -v openssl >/dev/null 2>&1 || skip_or_fail "openssl not found"
[[ $(openssl version) =~ ^OpenSSL\ ([3-9]|[1-9][0-9])\. ]] || skip_or_fail "OpenSSL 3.0 or newer needed: $(openssl version)"

cd "$REPO/compose/pki"
# Keep the source folder clean: no __pycache__ next to the scripts.
PYTHONDONTWRITEBYTECODE=1 TMPDIR=$(harness_native_path "$(harness_run_dir tmp)") \
  "$python" -m unittest discover -s . -p 'test_*.py'
