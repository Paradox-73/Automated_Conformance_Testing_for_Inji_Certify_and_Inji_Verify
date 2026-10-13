#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
#
# The CI job of one component on this machine, with the layout the workflow uploads:
#
#   bash scripts/ci-local.sh certify|verify [RUN-CONFORMANCE OPTIONS]
#
# Steps, as in .github/workflows/full-stack-conformance.yml: "bash scripts/check.sh all" (strict), the prepare step
# (pull, runner and testrig images), "./run-conformance.sh --component <c> --out ci-<c>", the job summary, and the
# removal of key material. The artifact folder is $HARNESS_RUN_DIR/ci-local/conformance-<c>/ (the workflow's
# artifact conformance-<c>), with summary.md next to it. The exit code is the first failing step's.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

component=${1:-}
[[ $component == certify || $component == verify ]] || die "usage: bash scripts/ci-local.sh certify|verify [OPTIONS]" 2
shift

out_name=ci-$component
reports=$(harness_run_dir reports)
artifact=$(harness_run_dir ci-local)/conformance-$component
if [[ -e $reports/$out_name ]]; then
  log_info "removing the previous $reports/$out_name"
  rm -rf -- "${reports:?}/$out_name"
fi

log_info "step 1/4: bash scripts/check.sh all (strict)"
CI=true bash "$HARNESS_ROOT/scripts/check.sh" all

log_info "step 2/4: prepare (pull, runner and testrig images)"
bash "$HARNESS_ROOT/run-full-stack-conformance.sh" --prepare-only

log_info "step 3/4: ./run-conformance.sh --component $component $*"
set +e
bash "$HARNESS_ROOT/run-conformance.sh" --component "$component" --out "$out_name" "$@"
code=$?
set -e

log_info "step 4/4: artifact"
rm -rf -- "$artifact"
mkdir -p "$artifact"
cp -R "$reports/$out_name/." "$artifact/"
# The suite's exports, the extracted HTML pages too, contain the configuration with the run's private keys.
rm -rf "$artifact"/*/suite-scripts "$artifact"/*/exports
if [[ -f $artifact/report/summary.md ]]; then
  cp "$artifact/report/summary.md" "$artifact/../summary-$component.md"
fi
log_info "artifact: $artifact (exit code $code)"
exit "$code"
