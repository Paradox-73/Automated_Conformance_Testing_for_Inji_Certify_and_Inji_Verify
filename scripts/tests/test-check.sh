#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# Tests for scripts/check.sh. Each case builds a throwaway git repository under $HARNESS_RUN_DIR/tmp, copies the
# check script into it, plants files and asserts the printed result and the exit status. No network access.
#
#   bash scripts/tests/test-check.sh
#
# "bash scripts/check.sh shell" runs this file. The planted secrets are assembled at run time from pieces, so this
# file itself never contains a string that a secret scanner would report.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
# shellcheck source=../lib/common.sh
source "$REPO/scripts/lib/common.sh"

WORK=$(mktemp -d "$(harness_run_dir tmp)/test-check.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

TESTS=0 FAILURES=0

# new_repo NAME: create an empty repository with the check scripts; print its path.
new_repo() {
  local dir=$WORK/$1
  mkdir -p "$dir/scripts/lib"
  git -C "$dir" init -q
  git -C "$dir" config core.autocrlf false
  cp "$REPO/scripts/check.sh" "$dir/scripts/"
  cp "$REPO/scripts/lib/common.sh" "$dir/scripts/lib/"
  printf '* -text\n' >"$dir/.gitattributes"
  printf '/run/\n' >"$dir/.gitignore"
  printf '%s\n' "$dir"
}

# run_check DIR ARGS...: run check.sh in DIR outside strict mode; sets OUT and RC.
run_check() {
  local dir=$1
  shift
  RC=0
  OUT=$(cd "$dir" && CI='' HARNESS_CHECK_STRICT=0 HARNESS_RUN_DIR="$dir/run" bash scripts/check.sh "$@" 2>&1) || RC=$?
}

failed() {
  FAILURES=$((FAILURES + 1))
  printf 'not ok %d - %s: %s\n' "$TESTS" "$1" "$2"
  printf '%s\n' "$OUT" | sed 's/^/    | /'
}

# expect NAME DIR CHECK STATUS [TEXT]: the check prints STATUS (PASS, FAIL or SKIP), exits with the matching
# status, and its output contains TEXT when given.
expect() {
  local name=$1 dir=$2 check=$3 want=$4 text=${5:-} want_rc=0
  TESTS=$((TESTS + 1))
  [[ $want == FAIL ]] && want_rc=1
  run_check "$dir" "$check"
  if ! grep -q "^$want  $check " <<<"$OUT"; then
    failed "$name" "expected $want for $check"
  elif ((RC != want_rc)); then
    failed "$name" "expected exit status $want_rc, got $RC"
  elif [[ -n $text && $OUT != *"$text"* ]]; then
    failed "$name" "output lacks: $text"
  else
    printf 'ok %d - %s\n' "$TESTS" "$name"
  fi
}

# refute_output NAME TEXT: the previous run's output does not contain TEXT.
refute_output() {
  TESTS=$((TESTS + 1))
  if [[ $OUT == *"$2"* ]]; then
    failed "$1" "output contains: $2"
  else
    printf 'ok %d - %s\n' "$TESTS" "$1"
  fi
}

# Secret material, assembled so that this file does not contain it literally.
DASHES=-----
PEM_KEY="${DASHES}BEGIN PRIVATE KEY${DASHES}
MC4CAQAwBQYDK2VwBCIEIKeyMaterialForTestsOnly000000000000000000
${DASHES}END PRIVATE KEY${DASHES}"
JWK_D=$(printf 'Q%.0s' {1..43})
AWS_KEY="AKIA$(printf 'Z%.0s' {1..16})"
PLANTED_VALUE="planted-$RANDOM-value"

# --- eol --------------------------------------------------------------------------------------------------------

repo=$(new_repo eol-clean)
expect "eol passes on LF files" "$repo" eol PASS "text files use LF"

repo=$(new_repo eol-crlf)
printf 'first\r\nsecond\r\n' >"$repo/notes.txt"
expect "eol rejects a CRLF team file" "$repo" eol FAIL "notes.txt: CRLF line endings"

repo=$(new_repo eol-ignored)
mkdir -p "$repo/run"
printf 'first\r\n' >"$repo/run/state.txt"
expect "eol ignores git-ignored files" "$repo" eol PASS

repo=$(new_repo eol-binary)
printf '\x89PNG\r\n\x1a\n\x00\x00binary\r\n' >"$repo/image.png"
expect "eol ignores binary files" "$repo" eol PASS

repo=$(new_repo eol-exempt)
mkdir -p "$repo/upstream"
printf 'upstream line\r\n' >"$repo/upstream/template.hbs"
printf '# comment\n%s upstream/template.hbs\n' "$(git -C "$repo" hash-object --no-filters upstream/template.hbs)" \
  >"$repo/scripts/eol-exempt.txt"
expect "eol exempts a listed byte-identical CRLF import" "$repo" eol PASS "1 byte-identical upstream CRLF files"
printf 'team edit\r\n' >>"$repo/upstream/template.hbs"
expect "eol rejects a listed CRLF import once it changes" "$repo" eol FAIL "CRLF file changed since import"

repo=$(new_repo eol-malformed)
printf 'not-a-blob-id some/path\n' >"$repo/scripts/eol-exempt.txt"
expect "eol rejects a malformed exemption line" "$repo" eol FAIL "malformed scripts/eol-exempt.txt"

# --- secrets ----------------------------------------------------------------------------------------------------

repo=$(new_repo secrets-clean)
# shellcheck disable=SC2016 # the ${...} reference is the planted text, not an expansion
printf 'password=${DB_PASSWORD}\nauth_token=https://issuer.example/token\n' >"$repo/app.properties"
expect "secrets passes on variable references and URLs" "$repo" secrets PASS "no findings"

repo=$(new_repo secrets-pem)
printf '%s\n' "$PEM_KEY" >"$repo/key.txt"
expect "secrets finds a PEM private key" "$repo" secrets FAIL "key.txt:1: private-key-pem"
refute_output "secrets never prints the key material" "KeyMaterialForTestsOnly"

printf 'version: 2\nsecret:\n  ignored-paths:\n    # test-only fixture\n    - "key.txt"\n' >"$repo/.gitguardian.yaml"
expect "secrets honours .gitguardian.yaml ignored-paths" "$repo" secrets PASS "1 files skipped as fixtures listed"

repo=$(new_repo secrets-glob)
mkdir -p "$repo/fixtures/deep"
printf '%s\n' "$PEM_KEY" >"$repo/fixtures/deep/key.txt"
printf 'version: 2\nsecret:\n  ignored-paths:\n    - fixtures/*  # whole folder\n' >"$repo/.gitguardian.yaml"
expect "secrets matches ignored-paths globs across folders" "$repo" secrets PASS

repo=$(new_repo secrets-jwk)
printf '{"kty": "OKP", "crv": "Ed25519", "d": "%s"}\n' "$JWK_D" >"$repo/key.json"
expect "secrets finds a private JWK" "$repo" secrets FAIL "key.json:1: private-jwk"

repo=$(new_repo secrets-password)
printf 'db.user=app\ndb.password=%s\n' "$PLANTED_VALUE" >"$repo/app.properties"
expect "secrets finds a password in a properties file" "$repo" secrets FAIL "app.properties:2: credential-assignment"
refute_output "secrets never prints the password" "$PLANTED_VALUE"

repo=$(new_repo secrets-ggignore)
printf 'db.password=%s # ggignore\n' "$PLANTED_VALUE" >"$repo/app.properties"
expect "secrets skips lines marked ggignore" "$repo" secrets PASS

repo=$(new_repo secrets-source)
printf 'class A { String password = "%s"; }\n' "$PLANTED_VALUE" >"$repo/A.java"
expect "secrets leaves source-code assignments alone" "$repo" secrets PASS

repo=$(new_repo secrets-token)
printf 'Use key %s here.\n' "$AWS_KEY" >"$repo/notes.md"
expect "secrets finds an access token in any text file" "$repo" secrets FAIL "notes.md:1: access-token"

repo=$(new_repo secrets-keystore)
printf '\x30\x82\x00\x00binary' >"$repo/client.p12"
expect "secrets rejects a key store file" "$repo" secrets FAIL "client.p12: key store or private key file"

# --- driver -----------------------------------------------------------------------------------------------------

repo=$(new_repo driver)
expect "inputs that do not exist skip, also in strict mode" "$repo" runner SKIP "no runner/pyproject.toml"

TESTS=$((TESTS + 1))
run_check "$repo" --strict testrigs
if ((RC == 0)) && grep -q '^SKIP  testrigs ' <<<"$OUT"; then
  printf 'ok %d - %s\n' "$TESTS" "--strict keeps missing inputs a SKIP"
else
  failed "--strict keeps missing inputs a SKIP" "expected SKIP and exit status 0"
fi

TESTS=$((TESTS + 1))
run_check "$repo" nonsense
if ((RC == 2)) && [[ $OUT == *"unknown check: nonsense"* ]]; then
  printf 'ok %d - %s\n' "$TESTS" "an unknown check is a usage error (exit status 2)"
else
  failed "an unknown check is a usage error (exit status 2)" "got exit status $RC"
fi

TESTS=$((TESTS + 1))
run_check "$repo" all
lines=$(grep -c -E '^(PASS|FAIL|SKIP)  ' <<<"$OUT" || true)
if ((RC == 0 && lines == 7)) && [[ $OUT == *"checks: "* ]]; then
  printf 'ok %d - %s\n' "$TESTS" "all prints one line per check and a summary"
else
  failed "all prints one line per check and a summary" "exit status $RC, $lines result lines"
fi

printf '%d tests, %d failed\n' "$TESTS" "$FAILURES"
((FAILURES == 0))
