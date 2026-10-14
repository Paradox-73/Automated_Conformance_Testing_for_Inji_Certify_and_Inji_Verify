#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
#
# The whole stack in one command: pull every image and build the runner (and testrig) images, then run both plans
# against Inji Certify and Inji Verify with ./run-conformance.sh --combined. The exit code is the gate's.
#
#   ./run-full-stack-conformance.sh                 prepare, then the combined run
#   ./run-full-stack-conformance.sh --prepare-only  only pull and build (about 2 GB the first time)
#   ./run-full-stack-conformance.sh --no-prepare [RUN-CONFORMANCE OPTIONS]
#
# Every other option goes to run-conformance.sh, for example --runner-only, --serial, --track haip, --keep-stack.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/lib/common.sh
source "$SCRIPT_DIR/scripts/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: ./run-full-stack-conformance.sh [--prepare-only | --no-prepare] [RUN-CONFORMANCE OPTIONS]

  --prepare-only   pull the images of every profile and build the runner and testrig images, then stop
  --no-prepare     skip pulling and building (the images are already there)
  -h, --help       this text

Without either option it prepares and then runs ./run-conformance.sh --combined with the other options, for
example --runner-only, --serial, --allow-stale, --track haip, --keep-stack. See ./run-conformance.sh --help.

Examples:
  ./run-full-stack-conformance.sh --prepare-only
  ./run-full-stack-conformance.sh --no-prepare --runner-only
  ./run-full-stack-conformance.sh --no-prepare
EOF
}

PREPARE=1 RUN=1 PASS=()
while (($#)); do
  case $1 in
    --prepare-only) RUN=0 && shift ;;
    --no-prepare) PREPARE=0 && shift ;;
    -h | --help) usage && exit 0 ;;
    --component | --combined) die "$1: this script always runs both components (use ./run-conformance.sh for one)" 2 ;;
    *) PASS+=("$1") && shift ;;
  esac
done
((PREPARE || RUN)) || die "--prepare-only and --no-prepare together leave nothing to do" 2

prepare() {
  harness_require_cmd docker "install Docker Desktop, or Docker Engine with the Compose plugin"
  docker info >/dev/null 2>&1 || die "the Docker daemon does not answer; start Docker" 3
  local logs started
  logs=$(harness_run_dir logs)
  started=$(date -u +%s)
  log_info "pulling the images of every profile (log: $logs/prepare-pull.log)"
  dc --profile verify --profile certify --profile reports --profile tools pull --ignore-buildable \
    >"$logs/prepare-pull.log" 2>&1 || die "pull failed; see $logs/prepare-pull.log" 3
  log_info "building the runner image (log: $logs/prepare-build.log)"
  dc --profile tools build runner >"$logs/prepare-build.log" 2>&1 || die "runner build failed; see $logs/prepare-build.log" 3
  log_info "building the testrig jars and image (log: $logs/prepare-testrig.log)"
  bash "$HARNESS_ROOT/testrigs/build.sh" --image >"$logs/prepare-testrig.log" 2>&1 ||
    die "testrig build failed; see $logs/prepare-testrig.log" 3
  log_info "prepared in $(($(date -u +%s) - started)) s"
}

((PREPARE)) && prepare
((RUN)) || exit 0
HARNESS_ENTRY_COMMAND=./run-full-stack-conformance.sh exec bash "$HARNESS_ROOT/run-conformance.sh" --combined "${PASS[@]}"
