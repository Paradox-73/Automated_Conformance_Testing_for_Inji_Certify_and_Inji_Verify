#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# Tests for testrigs/run-testrig.sh. A stub "docker" first on PATH answers the image, network and ps queries and
# records the arguments of "docker run", so no Docker daemon is needed.
#
#   bash scripts/tests/test-testrig.sh
#
# "bash scripts/check.sh shell" runs this file.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
# shellcheck source=../lib/common.sh
source "$REPO/scripts/lib/common.sh"

WORK=$(mktemp -d "$(harness_run_dir tmp)/test-testrig.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/bin"
cat >"$WORK/bin/docker" <<'EOF'
#!/usr/bin/env bash
case $1 in
  run) printf '%s\n' "$@" >"$STUB_LOG" ;;
  *) ;; # image inspect, network inspect: found; ps -q: nothing running
esac
EOF
chmod +x "$WORK/bin/docker"

TESTS=0 FAILURES=0

check() {
  TESTS=$((TESTS + 1))
  if [[ $2 == "$3" ]]; then
    printf 'ok %d - %s\n' "$TESTS" "$1"
  else
    FAILURES=$((FAILURES + 1))
    printf 'not ok %d - %s: expected [%s], got [%s]\n' "$TESTS" "$1" "$3" "$2"
  fi
}

# rig COMPONENT [ENDPOINT]: run-testrig.sh --invoke with the stub; prints the -D options docker run received.
rig() {
  # An empty TESTRIG_ENDPOINT means the default, as unset does.
  PATH="$WORK/bin:$PATH" STUB_LOG="$WORK/stub.log" HARNESS_RUN_DIR="$WORK/run" TESTRIG_ENDPOINT=${2:-} \
    bash "$REPO/testrigs/run-testrig.sh" "$1" --invoke --out "$WORK/out-$1" >/dev/null 2>&1 || true
  grep '^-D' "$WORK/stub.log"
  rm -f "$WORK/stub.log"
}

option() { sed -n "s/^-D$1=//p"; }

props=$(rig certify)
check "certify: env.endpoint is the compose issuer" "$(option env.endpoint <<<"$props")" "https://certify.inji.test:18450"
check "certify: the runner's target is env.endpoint" "$(option conformance.runner.command <<<"$props")" \
  "inji-conformance run --component {component} --target {target} --out {out}"

props=$(rig verify)
check "verify: env.endpoint is the compose verifier" "$(option env.endpoint <<<"$props")" "https://verify.inji.test:18451"
check "verify: the runner's target is env.endpoint plus the API path" "$(option conformance.runner.command <<<"$props")" \
  "inji-conformance run --component {component} --target {target}/v1/verify --out {out}"

props=$(rig verify https://verify.example.test:9443)
check "TESTRIG_ENDPOINT sets env.endpoint, which the runner's target follows" \
  "$(option env.endpoint <<<"$props")" "https://verify.example.test:9443"

# The rig must run as the user the compose services run as, or it cannot read the run's keys in invoke mode.
PATH="$WORK/bin:$PATH" STUB_LOG="$WORK/stub.log" HARNESS_RUN_DIR="$WORK/run" HARNESS_UID=1234 HARNESS_GID=5678 \
  bash "$REPO/testrigs/run-testrig.sh" verify --invoke --out "$WORK/out-user" >/dev/null 2>&1 || true
check "the rig runs as HARNESS_UID:HARNESS_GID" "$(grep -A1 '^-u$' "$WORK/stub.log")" "$(printf -- '-u\n1234:5678')"
rm -f "$WORK/stub.log"
PATH="$WORK/bin:$PATH" STUB_LOG="$WORK/stub.log" HARNESS_RUN_DIR="$WORK/run" \
  bash "$REPO/testrigs/run-testrig.sh" verify --invoke --out "$WORK/out-user" >/dev/null 2>&1 || true
check "the rig runs as the same default user as dc.sh" "$(grep -A1 '^-u$' "$WORK/stub.log" | tail -n 1)" \
  "$(harness_container_user)"
rm -f "$WORK/stub.log"

props=$(PATH="$WORK/bin:$PATH" STUB_LOG="$WORK/stub.log" HARNESS_RUN_DIR="$WORK/run" \
  bash "$REPO/testrigs/run-testrig.sh" certify --results /nonexistent 2>&1 || true)
check "consume mode still refuses a missing results file" "${props##*: }" "/nonexistent"

if ((FAILURES)); then
  printf '%d of %d testrig tests failed\n' "$FAILURES" "$TESTS"
  exit 1
fi
printf 'all %d testrig tests passed\n' "$TESTS"
