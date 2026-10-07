#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# Tests for scripts/dc.sh. A stub "docker" first on PATH records the arguments and environment it is called with,
# so no Docker daemon is needed. Each case uses its own run folder under $HARNESS_RUN_DIR/tmp.
#
#   bash scripts/tests/test-dc.sh
#
# "bash scripts/check.sh shell" runs this file.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
# shellcheck source=../lib/common.sh
source "$REPO/scripts/lib/common.sh"

WORK=$(mktemp -d "$(harness_run_dir tmp)/test-dc.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

# Stub docker: one argument per line, then the variables dc.sh exports for compose.
mkdir -p "$WORK/bin"
cat >"$WORK/bin/docker" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" >"$STUB_LOG"
printf 'HARNESS_RUN_DIR=%s\nHARNESS_UID=%s\nMSYS_NO_PATHCONV=%s\n' "$HARNESS_RUN_DIR" "$HARNESS_UID" \
  "${MSYS_NO_PATHCONV:-}" >>"$STUB_LOG"
EOF
chmod +x "$WORK/bin/docker"

TESTS=0 FAILURES=0

ok() {
  printf 'ok %d - %s\n' "$TESTS" "$1"
}
not_ok() {
  FAILURES=$((FAILURES + 1))
  printf 'not ok %d - %s: %s\n' "$TESTS" "$1" "$2"
}

# run_dc RUN_DIR ARGS...: run dc.sh with the stub; sets OUT (stdout and stderr), RC and LOG (stub record).
run_dc() {
  local run_dir=$1
  shift
  RC=0
  OUT=$(PATH="$WORK/bin:$PATH" STUB_LOG="$WORK/stub.log" HARNESS_RUN_DIR="$run_dir" \
    HARNESS_COMPOSE_PROJECT=${PROJECT:-ps01-harness} bash "$REPO/scripts/dc.sh" "$@" 2>&1) || RC=$?
  LOG=$(cat "$WORK/stub.log" 2>/dev/null || true)
  rm -f "$WORK/stub.log"
}

# value NAME FILE: the value of NAME= in an env file.
value() {
  sed -n "s/^$1=//p" "$2"
}

generated_names=(VERIFY_DB_PASSWORD CERTIFY_DB_PASSWORD CERTIFY_KEYSTORE_PASSWORD MINIO_ROOT_PASSWORD)

# --- first call creates env.local and the mounted folders ----------------------------------------------------------
run_dir=$WORK/run1
TESTS=$((TESTS + 1))
name="first call creates env.local with a 32-hex password for every generated name"
run_dc "$run_dir" config -q
bad=0
for s in "${generated_names[@]}"; do
  [[ $(value "$s" "$run_dir/env.local") =~ ^[0-9a-f]{32}$ ]] || bad=1
done
if ((RC == 0 && bad == 0)); then ok "$name"; else not_ok "$name" "exit $RC, output: $OUT"; fi

TESTS=$((TESTS + 1))
name="passwords differ from each other"
distinct=$(for s in "${generated_names[@]}"; do value "$s" "$run_dir/env.local"; done | sort -u | wc -l)
if ((distinct == ${#generated_names[@]})); then ok "$name"; else not_ok "$name" "$distinct distinct values"; fi

TESTS=$((TESTS + 1))
name="pki and reports folders exist before compose runs"
if [[ -d $run_dir/pki && -d $run_dir/reports ]]; then ok "$name"; else not_ok "$name" "missing folder"; fi

TESTS=$((TESTS + 1))
name="env.local is readable by its owner only"
if harness_is_windows; then
  ok "$name # SKIP file modes are not enforced on Windows"
elif [[ $(stat -c %a "$run_dir/env.local" 2>/dev/null || stat -f %Lp "$run_dir/env.local") == 600 ]]; then
  ok "$name"
else
  not_ok "$name" "mode is not 600"
fi

# --- compose arguments --------------------------------------------------------------------------------------------
TESTS=$((TESTS + 1))
name="compose gets the project name, the root compose file and the env file, then the caller's arguments"
root=$(harness_native_path "$REPO")
native_run=$(harness_native_path "$run_dir")
expected=$(printf '%s\n' compose --project-name ps01-harness --project-directory "$root" --file \
  "$root/docker-compose.yml" --env-file "$native_run/env.local" config -q)
if [[ $(head -n 11 <<<"$LOG") == "$expected" ]]; then ok "$name"; else not_ok "$name" "got: $LOG"; fi

TESTS=$((TESTS + 1))
name="HARNESS_RUN_DIR reaches compose as a native path, with Git Bash path rewriting off"
if grep -qx "HARNESS_RUN_DIR=$native_run" <<<"$LOG" && grep -qx "MSYS_NO_PATHCONV=1" <<<"$LOG" &&
  grep -qE '^HARNESS_UID=[0-9]+$' <<<"$LOG"; then
  ok "$name"
else
  not_ok "$name" "got: $LOG"
fi

TESTS=$((TESTS + 1))
name="arguments with spaces reach compose unchanged"
run_dc "$run_dir" run --rm probe -H 'Content-Type: application/json' /v1/verify
if [[ $(tail -n 9 <<<"$LOG" | head -n 6) == "$(printf '%s\n' run --rm probe -H 'Content-Type: application/json' \
  /v1/verify)" ]]; then
  ok "$name"
else
  not_ok "$name" "got: $LOG"
fi

# --- later calls keep existing values -----------------------------------------------------------------------------
TESTS=$((TESTS + 1))
name="a second call keeps every existing password"
before=$(cat "$run_dir/env.local")
run_dc "$run_dir" ps
if ((RC == 0)) && [[ $(cat "$run_dir/env.local") == "$before" ]]; then ok "$name"; else not_ok "$name" "env.local changed"; fi

TESTS=$((TESTS + 1))
name="a missing name is appended and the other values stay"
keep=$(value VERIFY_DB_PASSWORD "$run_dir/env.local")
grep -v '^MINIO_ROOT_PASSWORD=' "$run_dir/env.local" >"$WORK/env.tmp"
mv "$WORK/env.tmp" "$run_dir/env.local"
run_dc "$run_dir" ps
if [[ $(value VERIFY_DB_PASSWORD "$run_dir/env.local") == "$keep" &&
  $(value MINIO_ROOT_PASSWORD "$run_dir/env.local") =~ ^[0-9a-f]{32}$ && $OUT == *"generated MINIO_ROOT_PASSWORD"* ]]; then
  ok "$name"
else
  not_ok "$name" "output: $OUT"
fi

TESTS=$((TESTS + 1))
name="values set by hand (image overrides) are kept"
printf 'VERIFY_IMAGE=example/verify:test\n' >>"$run_dir/env.local"
run_dc "$run_dir" ps
if grep -qx 'VERIFY_IMAGE=example/verify:test' "$run_dir/env.local"; then ok "$name"; else not_ok "$name" "lost"; fi

TESTS=$((TESTS + 1))
name="no lock folder or temporary file is left behind"
if [[ -z $(find "$run_dir" -maxdepth 1 -name 'env.local.*') ]]; then ok "$name"; else not_ok "$name" "leftovers"; fi

# --- down stops every profile ---------------------------------------------------------------------------------------
# caller_args: the arguments compose got after the four harness options (8 lines), without the stub's 3 env lines.
caller_args() {
  tail -n +10 <<<"$LOG" | head -n -3
}

TESTS=$((TESTS + 1))
name="down without a profile gets --profile '*', so services started with a profile stop too"
run_dc "$WORK/run1" down -v
if ((RC == 0)) && [[ $(caller_args) == "$(printf '%s\n' --profile '*' down -v)" ]]; then
  ok "$name"
else
  not_ok "$name" "exit $RC, got: $(caller_args)"
fi

TESTS=$((TESTS + 1))
name="down with a named profile is passed unchanged"
run_dc "$WORK/run1" --profile verify down -v
if [[ $(caller_args) == "$(printf '%s\n' --profile verify down -v)" ]]; then
  ok "$name"
else
  not_ok "$name" "got: $(caller_args)"
fi

TESTS=$((TESTS + 1))
name="down as an argument of another subcommand is left alone"
run_dc "$WORK/run1" run --rm runner sh -c down
if [[ $(caller_args) == "$(printf '%s\n' run --rm runner sh -c down)" ]]; then
  ok "$name"
else
  not_ok "$name" "got: $(caller_args)"
fi

TESTS=$((TESTS + 1))
name="an option value that reads 'down' is not taken for the subcommand"
run_dc "$WORK/run1" --progress down ps
if [[ $(caller_args) == "$(printf '%s\n' --progress down ps)" ]]; then
  ok "$name"
else
  not_ok "$name" "got: $(caller_args)"
fi

# --- refusals -----------------------------------------------------------------------------------------------------
TESTS=$((TESTS + 1))
name="a project name outside ps01-* is refused with exit status 2"
PROJECT=other-project run_dc "$WORK/run2" config -q
if ((RC == 2)) && [[ -z $LOG ]]; then ok "$name"; else not_ok "$name" "exit $RC"; fi

printf '%d tests, %d failed\n' "$TESTS" "$FAILURES"
((FAILURES == 0))
