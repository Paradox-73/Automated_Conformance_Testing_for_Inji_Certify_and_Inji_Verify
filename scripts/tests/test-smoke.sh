#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# Tests for the parts of compose/smoke.sh that run without Docker: argument handling, the memory peak
# calculation from "docker stats" samples, and the small JSON and JWT helpers.
#
#   bash scripts/tests/test-smoke.sh
#
# "bash scripts/check.sh shell" runs this file. The full smoke test needs Docker: bash compose/smoke.sh verify.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
# shellcheck source=../../compose/smoke.sh
source "$REPO/compose/smoke.sh"
set +e # sourcing turned on errexit; the checks below look at exit statuses themselves

WORK=$(mktemp -d "$(harness_run_dir tmp)/test-smoke.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

TESTS=0 FAILURES=0

# check NAME GOT WANT
check() {
  TESTS=$((TESTS + 1))
  if [[ $2 == "$3" ]]; then
    printf 'ok %d - %s\n' "$TESTS" "$1"
  else
    FAILURES=$((FAILURES + 1))
    printf 'not ok %d - %s\n    got:  %s\n    want: %s\n' "$TESTS" "$1" "${2//$'\n'/|}" "${3//$'\n'/|}"
  fi
}

# --- arguments (the script exits before it touches Docker) ---------------------------------------------------------
bash "$REPO/compose/smoke.sh" >/dev/null 2>&1
check "no profile is a usage error" "$?" 2
bash "$REPO/compose/smoke.sh" verify nonsense >/dev/null 2>&1
check "an unknown profile is a usage error" "$?" 2
out=$(bash "$REPO/compose/smoke.sh" --help)
check "--help exits 0 and lists the profiles" "$?:$(grep -c 'Profiles: suite verify' <<<"$out")" "0:1"

# --- peak memory from docker stats samples -------------------------------------------------------------------------
OUT_DIR=$WORK
tab=$'\t'
{
  printf '1%sps01-harness-suite-server-1%s412.5MiB / 1.5GiB\n' "$tab" "$tab"
  printf '2%sps01-harness-suite-server-1%s1.25GiB / 1.5GiB\n' "$tab" "$tab"
  printf '1%sps01-harness-tls-proxy-1%s6144KiB / 128MiB\n' "$tab" "$tab"
  printf '1%sps01-harness-probe-run-0a1b2c%s30MiB / 64MiB\n' "$tab" "$tab"
  printf '1%sps01-harness-pki-init-1%s0B / 0B\n' "$tab" "$tab"
  printf '2%sps01-harness-verify-db-1%s52428800B / 256MiB\n' "$tab" "$tab"
} >"$WORK/stats.tsv"
check "peaks per service in MiB, highest first; run containers and 0 B left out" "$(peak_memory)" \
  "$(printf 'suite-server 1280\nverify-db 50\ntls-proxy 6')"

rm -f "$WORK/stats.tsv"
check "no samples give no peaks" "$(peak_memory)" ""

# --- helpers --------------------------------------------------------------------------------------------------------
check "json_string reads a string field" \
  "$(json_string requestUri <<<'{"transactionId":"txn_1","requestUri":"https://verify.inji.test:18451/v1/verify/v2/vp-request/req_1"}')" \
  "https://verify.inji.test:18451/v1/verify/v2/vp-request/req_1"
check "json_string prints nothing for a missing field" "$(json_string missing <<<'{"a":"b"}')" ""

# base64url of {"alg":"EdDSA","x5c":["MIIB"]} without padding, with the URL-safe alphabet.
header=$(printf '%s' '{"alg":"EdDSA","x5c":["MIIB"]}' | base64 | tr '+/' '-_' | tr -d '=\n')
check "b64url_decode restores a JWT header" "$(b64url_decode <<<"$header")" '{"alg":"EdDSA","x5c":["MIIB"]}'
check "b64url_decode handles '-' and '_'" "$(printf '%s' '-_-_' | b64url_decode | od -An -tx1 | tr -d ' ')" "fbffbf"

PROFILES=(verify)
has_profile verify
check "has_profile finds a given profile" "$?" 0
has_profile certify
check "has_profile rejects a profile that was not given" "$?" 1

printf '%d tests, %d failed\n' "$TESTS" "$FAILURES"
((FAILURES == 0))
