#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
# Tests for stack_merge_exit_code (scripts/lib/stack.sh), which run-conformance.sh uses to merge the runner's exit
# code with each testrig's. A regression (1) must never turn into a retryable 3.
#
#   bash scripts/tests/test-exit-codes.sh
#
# "bash scripts/check.sh shell" runs this file.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
# shellcheck source=../lib/common.sh
source "$REPO/scripts/lib/common.sh"
# shellcheck source=../lib/stack.sh
source "$REPO/scripts/lib/stack.sh"

TESTS=0 FAILURES=0
# runner rig expected
cases=(
  '0 0 0' '0 1 1' '0 2 3' '0 3 3'
  '1 0 1' '1 1 1' '1 2 1' '1 3 1'
  '3 0 3' '3 1 1' '3 2 3' '4 3 4' '4 1 1'
)
for case in "${cases[@]}"; do
  read -r runner rig expected <<<"$case"
  TESTS=$((TESTS + 1))
  got=$(stack_merge_exit_code "$runner" "$rig")
  if [[ $got == "$expected" ]]; then
    printf 'ok %d - runner %s, testrig %s: %s\n' "$TESTS" "$runner" "$rig" "$got"
  else
    FAILURES=$((FAILURES + 1))
    printf 'not ok %d - runner %s, testrig %s: expected %s, got %s\n' "$TESTS" "$runner" "$rig" "$expected" "$got"
  fi
done
printf '1..%d\n' "$TESTS"
((FAILURES == 0))
