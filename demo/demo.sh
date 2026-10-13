#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
#
# The demo: preflight, a full run of both components, where the results are; with --regression a second run of
# Inji Certify with a configuration-only regression, the failing gate, and the diff between the two runs.
#
#   bash demo/demo.sh                 the combined run (runner, testrig, MinIO), then the report paths
#   bash demo/demo.sh --regression    a passing Inji Certify run, the same with demo/regression.compose.yml (the
#                                     gate fails and names the modules), the diff, and back to normal
#   bash demo/demo.sh --runner-only   either of the above without the testrig step (faster)
#
# Exit status: 0 when the demo showed what it should (with --regression: the gate failed as intended), 1 otherwise.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../scripts/lib/common.sh
source "$SCRIPT_DIR/../scripts/lib/common.sh"

regression=0 extra=()
for arg in "$@"; do
  case $arg in
    --regression) regression=1 ;;
    --runner-only) extra+=(--runner-only) ;;
    -h | --help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//' && exit 0 ;;
    *) die "unknown option: $arg (see --help)" 2 ;;
  esac
done

step() { printf '\n==== %s\n' "$*"; }
stamp=$(date -u +%Y%m%dT%H%M%SZ)
reports=$(harness_run_dir reports)

if ((!regression)); then
  step "1/2 both plans against Inji Certify and Inji Verify, in parallel"
  set +e
  bash "$HARNESS_ROOT/run-conformance.sh" --combined "${extra[@]}" --out "demo-$stamp"
  code=$?
  set -e
  step "2/2 results"
  printf 'exit code %s; open %s/demo-%s/report/summary.html\n' "$code" "$reports" "$stamp"
  exit "$code"
fi

step "1/4 Inji Certify as configured: the gate passes"
set +e
bash "$HARNESS_ROOT/run-conformance.sh" --component certify "${extra[@]}" --out "demo-$stamp-before"
before=$?
step "2/4 the same Inji Certify image with demo/regression.compose.yml (a wrong issuer identifier)"
HARNESS_COMPOSE_FILES=demo/regression.compose.yml bash "$HARNESS_ROOT/run-conformance.sh" --component certify \
  "${extra[@]}" --out "demo-$stamp-regression" --compare "$reports/demo-$stamp-before"
after=$?
set -e
step "3/4 what changed between the two runs"
set +e
bash "$HARNESS_ROOT/scripts/dc.sh" run --rm --no-deps runner inji-conformance diff "/reports/demo-$stamp-before" \
  "/reports/demo-$stamp-regression"
changed=$?
set -e
step "4/4 back to normal: the override was only in the environment of step 2"
printf 'gate before: exit %s; with the regression: exit %s; diff: exit %s (16 = the runs differ)\n' "$before" \
  "$after" "$changed"
printf 'reports: %s/demo-%s-regression/report/summary.html and diff.html\n' "$reports" "$stamp"
if ((before == 0 && after == 1 && changed == 16)); then
  printf 'demo ok: the gate caught the regression and the diff names the modules\n'
  exit 0
fi
printf 'demo did not go as expected\n' >&2
exit 1
