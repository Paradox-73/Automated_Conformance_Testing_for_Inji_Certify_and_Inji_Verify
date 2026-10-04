#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# Tests for third_party/reimport.sh. The real import is checked in place; every other case copies the script into
# a throwaway repository under $HARNESS_RUN_DIR/tmp and runs it against a local stand-in for the upstream suite
# repository (a file:// remote), so no network access is needed.
#
#   bash scripts/tests/test-reimport.sh
#
# "bash scripts/check.sh shell" runs this file.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
# shellcheck source=../lib/common.sh
source "$REPO/scripts/lib/common.sh"

WORK=$(mktemp -d "$(harness_run_dir tmp)/test-reimport.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

TESTS=0 FAILURES=0
IMPORTED=(LICENSE.txt scripts/compare-results.py scripts/conformance.py scripts/requirements.txt
  scripts/run-test-plan.py scripts/test_plan_parser.py)

# run DIR ARGS...: run DIR/third_party/reimport.sh with ARGS; sets OUT and RC. The extra environment is passed by
# the caller with "env" in front of run when needed.
run() {
  local dir=$1
  shift
  RC=0
  OUT=$(HARNESS_RUN_DIR="$WORK/run" bash "$dir/third_party/reimport.sh" "$@" 2>&1) || RC=$?
}

ok() { printf 'ok %d - %s\n' "$TESTS" "$1"; }
not_ok() {
  FAILURES=$((FAILURES + 1))
  printf 'not ok %d - %s: %s\n' "$TESTS" "$1" "$2"
  printf '%s\n' "$OUT" | sed 's/^/    | /'
}

# expect NAME WANT_RC [TEXT]: the last run exited with WANT_RC and printed TEXT (a fixed string) when given.
expect() {
  local name=$1 want_rc=$2 text=${3:-}
  TESTS=$((TESTS + 1))
  if ((RC != want_rc)); then
    not_ok "$name" "expected exit status $want_rc, got $RC"
  elif [[ -n $text ]] && ! grep -qF -- "$text" <<<"$OUT"; then
    not_ok "$name" "output lacks: $text"
  else
    ok "$name"
  fi
}

# assert NAME COMMAND...: a plain condition test.
assert() {
  local name=$1
  shift
  TESTS=$((TESTS + 1))
  if "$@"; then ok "$name"; else
    OUT="(condition failed: $*)"
    not_ok "$name" "condition failed"
  fi
}

# copy_repo NAME: a minimal repository holding the script, its helper library and the current import.
copy_repo() {
  local dir=$WORK/$1
  mkdir -p "$dir/scripts/lib" "$dir/third_party"
  cp "$REPO/scripts/lib/common.sh" "$dir/scripts/lib/"
  cp "$REPO/third_party/reimport.sh" "$dir/third_party/"
  cp -R "$REPO/third_party/oidf-conformance-suite" "$dir/third_party/"
  printf '%s\n' "$dir"
}

ug() { git -C "$WORK/upstream" -c core.autocrlf=false -c user.name=test -c user.email=test@example.invalid "$@"; }

# A stand-in for openid/conformance-suite with the six imported paths, plus the material that must stay out:
# scripts/certs-keys/ and a script that is not imported. conformance.py carries an export-subst placeholder and
# requirements.txt is stored with CRLF line endings, so a copy made with "git archive" or with line-ending
# conversion would differ from the stored blob.
make_upstream() {
  local up=$WORK/upstream f
  mkdir -p "$up/scripts/certs-keys"
  git -C "$up" init -q
  for f in "${IMPORTED[@]}"; do
    printf 'upstream %s, version 1\n' "$f" >"$up/$f"
  done
  # shellcheck disable=SC2016 # a literal git export-subst placeholder, not an expansion
  printf '# commit $Format:%%H$\n' >>"$up/scripts/conformance.py"
  printf 'httpx\r\npyparsing\r\n' >"$up/scripts/requirements.txt"
  printf 'scripts/conformance.py export-subst\n' >"$up/.gitattributes"
  printf 'not a real key\n' >"$up/scripts/certs-keys/test.key"
  printf 'print("not imported")\n' >"$up/scripts/run-security-tests.py"
  ug add -A
  ug commit -qm v1
  ug tag -a -m "release v1" release-test-1
  printf 'upstream run-test-plan.py, version 2\n' >"$up/scripts/run-test-plan.py"
  ug commit -qam v2
  ug tag release-test-2
}

# ---------------------------------------------------------------------------------------------------------------

# 1. The committed import matches its manifest.
run "$REPO" check
expect "repository import matches the manifest" 0 "6 files identical"

# 2. Local damage is reported, file by file.
dir=$(copy_repo damaged)
printf '#' >>"$dir/third_party/oidf-conformance-suite/scripts/conformance.py"
sed -i 's/$/\r/' "$dir/third_party/oidf-conformance-suite/LICENSE.txt"
rm "$dir/third_party/oidf-conformance-suite/scripts/requirements.txt"
mkdir -p "$dir/third_party/oidf-conformance-suite/scripts/certs-keys"
printf 'x\n' >"$dir/third_party/oidf-conformance-suite/scripts/certs-keys/client.key"
run "$dir" check
expect "edited file is reported" 1 "changed: scripts/conformance.py"
expect "CRLF conversion is reported" 1 "changed: LICENSE.txt"
expect "deleted file is reported" 1 "missing: scripts/requirements.txt"
expect "extra upstream key material is reported" 1 "not in the manifest: scripts/certs-keys/client.key"

# 3. Usage errors.
run "$REPO"
expect "no command is a usage error" 2 "Exit status"
run "$REPO" import
expect "import without REF is a usage error" 2

# 4. Import from the stand-in upstream, with core.autocrlf=true as on a default Git for Windows install.
make_upstream
dir=$(copy_repo cycle)
export OIDF_SUITE_URL="file://$WORK/upstream" OIDF_SUITE_CLONE="$WORK/clone"
GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.autocrlf GIT_CONFIG_VALUE_0=true run "$dir" import release-test-1
expect "import of an annotated tag succeeds" 0 "import: upstream openid/conformance-suite@$(ug rev-parse 'release-test-1^{commit}') (MIT)"
same=1
for f in "${IMPORTED[@]}"; do
  [[ $(git hash-object --no-filters "$dir/third_party/oidf-conformance-suite/$f") == "$(ug rev-parse "release-test-1:$f")" ]] || same=0
done
assert "imported files are byte-identical to the upstream blobs" test "$same" = 1
assert "certs-keys is not imported" test ! -e "$dir/third_party/oidf-conformance-suite/scripts/certs-keys"
assert "unlisted upstream scripts are not imported" test ! -e "$dir/third_party/oidf-conformance-suite/scripts/run-security-tests.py"
assert "manifest records the tag" grep -qx 'SUITE_REF=release-test-1' "$dir/third_party/reimport.sh"
run "$dir" check
expect "check passes after import" 0 "6 files identical"
run "$dir" verify
expect "verify passes after import" 0 "manifest matches"

# 5. A tag moved upstream after the import is caught by verify.
ug tag -f -a -m "moved" release-test-1 release-test-2 >/dev/null
run "$dir" verify
expect "moved tag is reported" 1 "tag release-test-1 now points at $(ug rev-parse 'release-test-2^{commit}') upstream"

# 6. Upgrading to a newer tag replaces changed files and leaves no stale ones.
printf 'stale\n' >"$dir/third_party/oidf-conformance-suite/scripts/stale.py"
run "$dir" import release-test-2
expect "import of a lightweight tag succeeds" 0
assert "changed upstream file is updated" grep -q 'version 2' "$dir/third_party/oidf-conformance-suite/scripts/run-test-plan.py"
assert "stale file is removed" test ! -e "$dir/third_party/oidf-conformance-suite/scripts/stale.py"
run "$dir" verify
expect "verify passes after the upgrade" 0 "manifest matches"

# 7. Unpinned or broken references are refused without touching the import.
run "$dir" import master
expect "branch names are refused" 2 "only tags and full commit ids"
ug rm -q scripts/compare-results.py
ug commit -qm v3
ug tag release-test-3
run "$dir" import release-test-3
expect "a release without an imported path is refused" 2 "has no file scripts/compare-results.py"
run "$dir" check
expect "refused import leaves the previous import intact" 0

if ((FAILURES)); then
  printf '%d of %d reimport tests failed\n' "$FAILURES" "$TESTS"
  exit 1
fi
printf 'all %d reimport tests passed\n' "$TESTS"
