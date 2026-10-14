#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
#
# One command for a conformance run: start the stack, run the suite's plans against Inji Certify and/or Inji Verify,
# run the api-testrig step, write the consolidated report, stop the stack. The exit code is the gate's.
#
#   ./run-conformance.sh --component certify|verify [OPTIONS] [RUNNER OPTIONS]
#   ./run-conformance.sh --combined [OPTIONS] [RUNNER OPTIONS]
#
# Run ./run-conformance.sh --help for the options and examples.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$SCRIPT_DIR/scripts/lib/common.sh"
# shellcheck source=scripts/lib/stack.sh
source "$SCRIPT_DIR/scripts/lib/stack.sh"

usage() {
  cat <<'EOF'
Usage: ./run-conformance.sh (--component certify|verify | --combined) [OPTIONS] [RUNNER OPTIONS]

Starts the compose stack, runs the OpenID conformance suite's plan(s) against Inji Certify (issuer plan) and/or
Inji Verify (verifier plan) with every handoff answered automatically, runs the api-testrig step, writes the
consolidated report and stops the stack. The exit code is the benchmark gate's.

Which component:
  --component certify     OpenID4VCI 1.0 issuer plan against Inji Certify
  --component verify      OpenID4VP 1.0 verifier plan against Inji Verify
  --combined              both, at the same time (add --serial for one after the other)

Options of this script:
  --runner-only           only the conformance runner: no testrig step and no MinIO
  --keep-stack            leave the stack running afterwards (stop it with: bash scripts/dc.sh --profile '*' down -v)
  --out NAME              run folder name below $HARNESS_RUN_DIR/reports (default: the run id)
  --compare DIR           earlier run folder to compare against in the report (writes diff.html)
  -h, --help              this text

Runner options (passed to "inji-conformance run" unchanged):
  --modules A,B           only these test modules
  --track gate|haip       gate (default): the 1.0 Final plans; haip: HAIP readiness plans, never gating
  --serial                with --combined: one plan after the other
  --allow-stale           stale benchmark entries warn instead of failing
  --variant NAME=VALUE    replace one variant value of the plan template (repeatable)
  --template NAME         a non-default plan template from conformance/plans
  --no-gate               record verdicts without applying the benchmark
  --no-seed               do not seed Inji Certify before the issuer plan
  --timeout-minutes N     time limit of the whole run (default 30)

Settings (environment): HARNESS_RUN_DIR, HARNESS_COMPOSE_FILES (comma-separated compose overrides, for example
demo/regression.compose.yml), image overrides such as CERTIFY_IMAGE (see CONTRIBUTING.md).

Examples:
  ./run-conformance.sh --component verify --runner-only
  ./run-conformance.sh --component certify --modules oid4vci-1_0-issuer-happy-flow --runner-only
  ./run-conformance.sh --combined
  ./run-conformance.sh --combined --runner-only --track haip
  HARNESS_COMPOSE_FILES=demo/regression.compose.yml ./run-conformance.sh --component certify --runner-only

Exit codes: 0 gate passed, 1 gate failed (regression or stale benchmark entry), 2 usage or configuration error,
3 environment not ready (Docker, ports, a service that did not start), 4 time limit reached.

Output in $HARNESS_RUN_DIR/reports/<run id>/: manifest.json, <component>/results.json, report/summary.html,
report/badge.svg, logs/, and with the testrig step testrig/<component>/.
EOF
}

COMPONENTS=() RUNNER_ARGS=() RUNNER_ONLY=0 KEEP_STACK=0 OUT_NAME='' COMPARE='' COMBINED=0
ORIGINAL_ARGS=("$@")

while (($#)); do
  case $1 in
    --component)
      [[ ${2:-} == certify || ${2:-} == verify ]] || die "--component needs certify or verify (see --help)" 2
      COMPONENTS=("$2")
      RUNNER_ARGS+=(--component "$2")
      shift 2
      ;;
    --combined)
      COMBINED=1 COMPONENTS=(certify verify)
      RUNNER_ARGS+=(--combined)
      shift
      ;;
    --runner-only) RUNNER_ONLY=1 && shift ;;
    --keep-stack) KEEP_STACK=1 && shift ;;
    --out)
      [[ ${2:-} =~ ^[A-Za-z0-9._-]+$ ]] || die "--out needs a plain folder name (it is created below \$HARNESS_RUN_DIR/reports)" 2
      OUT_NAME=$2 && shift 2
      ;;
    --compare)
      [[ -n ${2:-} ]] || die "--compare needs a run folder" 2
      COMPARE=$2 && shift 2
      ;;
    -h | --help) usage && exit 0 ;;
    --modules | --track | --variant | --template | --timeout-minutes)
      [[ -n ${2:-} ]] || die "$1 needs a value (see --help)" 2
      RUNNER_ARGS+=("$1" "$2") && shift 2
      ;;
    --serial | --allow-stale | --no-gate | --no-seed) RUNNER_ARGS+=("$1") && shift ;;
    *) die "unknown option: $1 (see --help)" 2 ;;
  esac
done
((${#COMPONENTS[@]})) || die "say which component: --component certify|verify or --combined (see --help)" 2
if ((COMBINED)) && [[ ${RUNNER_ARGS[*]} == *"--component"* ]]; then
  die "--component and --combined exclude each other" 2
fi

PROFILES=("${COMPONENTS[@]}")
((RUNNER_ONLY)) || PROFILES+=(reports)
PROFILE_ARGS=()
for profile in "${PROFILES[@]}"; do PROFILE_ARGS+=(--profile "$profile"); done

RUN_ID=$(stack_new_run_id)
OUT_NAME=${OUT_NAME:-$RUN_ID}
REPORTS=$(harness_run_dir reports)
OUT=$REPORTS/$OUT_NAME
[[ ! -e $OUT ]] || die "run folder $OUT exists already; choose another --out" 2
CONTAINER_OUT=/reports/$OUT_NAME
STARTED=$(date -u +%s)

# shellcheck disable=SC2329 # called by the EXIT trap
teardown() {
  local status=$?
  if ((KEEP_STACK)); then
    log_info "stack left running (--keep-stack); stop it with: bash scripts/dc.sh --profile '*' down -v"
  else
    dc logs --no-color >"$OUT/logs/compose.log" 2>&1 || true
    dc --profile '*' down -v >"$OUT/logs/compose-down.log" 2>&1 || log_warn "teardown failed: see $OUT/logs/compose-down.log"
    log_info "stack stopped and removed"
  fi
  exit "$status"
}

stack_preflight "${PROFILES[@]}"
mkdir -p "$OUT/logs"
trap teardown EXIT
trap 'exit 130' INT TERM

log_info "run $RUN_ID: ${COMPONENTS[*]}, profiles ${PROFILES[*]}; output in $OUT"
if ! dc "${PROFILE_ARGS[@]}" up -d --wait >"$OUT/logs/compose-up.log" 2>&1; then
  log_error "the stack did not become healthy; last lines of $OUT/logs/compose-up.log:"
  tail -n 15 "$OUT/logs/compose-up.log" >&2
  exit 3
fi
log_info "stack healthy after $(($(date -u +%s) - STARTED)) s"
stack_images_json "$OUT/images.json"

RUNNER_ENV=(
  -e "HARNESS_GIT_COMMIT=$(stack_git_commit)"
  -e "HARNESS_GIT_DIRTY=$(stack_git_dirty)"
  -e "HARNESS_IMAGES_FILE=$CONTAINER_OUT/images.json"
  -e "HARNESS_COMMAND=$(printf '%s\n' "${HARNESS_ENTRY_COMMAND:-./run-conformance.sh}" "${ORIGINAL_ARGS[@]}")"
  -e "HARNESS_HOST_OS=$(stack_host_os)"
)
set +e
dc run --rm "${RUNNER_ENV[@]}" runner inji-conformance run "${RUNNER_ARGS[@]}" --run-id "$RUN_ID" --out "$CONTAINER_OUT" 2>&1 |
  tee "$OUT/logs/runner.log"
RUNNER_CODE=${PIPESTATUS[0]}
set -e
log_info "runner exit code $RUNNER_CODE"
EXIT_CODE=$RUNNER_CODE

if ((!RUNNER_ONLY)); then
  for component in "${COMPONENTS[@]}"; do
    [[ -f $OUT/$component/results.json ]] || continue
    set +e
    bash "$HARNESS_ROOT/testrigs/run-testrig.sh" "$component" --results "$OUT/$component/results.json" \
      --out "$OUT/testrig/$component" 2>&1 | tee "$OUT/logs/testrig-$component.log"
    rig_code=${PIPESTATUS[0]}
    set -e
    log_info "testrig $component exit code $rig_code"
    ((rig_code <= EXIT_CODE)) || EXIT_CODE=$rig_code
  done
fi

REPORT_ARGS=(--run "$CONTAINER_OUT" --out "$CONTAINER_OUT/report")
((COMBINED)) && REPORT_ARGS+=(--combined)
if [[ -n $COMPARE ]]; then
  compare_dir=$(cd "$COMPARE" 2>/dev/null && pwd) || die "--compare: no such folder: $COMPARE" 2
  [[ $compare_dir == "$REPORTS"/* ]] || die "--compare must be a run folder below $REPORTS" 2
  REPORT_ARGS+=(--compare "/reports/${compare_dir#"$REPORTS"/}")
fi
if [[ -f $OUT/manifest.json ]]; then
  if ! dc run --rm runner inji-conformance report "${REPORT_ARGS[@]}" >"$OUT/logs/report.log" 2>&1; then
    log_warn "the report could not be written; see $OUT/logs/report.log"
  fi
else
  log_warn "no manifest.json (the runner did not finish): no report"
fi

printf '\nrun %s finished in %s s, exit code %s\n' "$RUN_ID" "$(($(date -u +%s) - STARTED))" "$EXIT_CODE"
printf '  run folder   %s\n' "$OUT"
for component in "${COMPONENTS[@]}"; do
  [[ -f $OUT/$component/results.json ]] && printf '  %-12s %s\n' "$component" "$OUT/$component/results.json"
done
[[ -f $OUT/report/summary.html ]] && printf '  report       %s\n  badge        %s\n' "$OUT/report/summary.html" "$OUT/report/badge.svg"
for component in "${COMPONENTS[@]}"; do
  [[ -f $OUT/testrig/$component/report.txt ]] && sed 's/^/  /' "$OUT/testrig/$component/report.txt"
done
exit "$EXIT_CODE"
