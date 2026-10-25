#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
#
# Run one Inji api-testrig's OpenID conformance suite (ConformanceRigRunner) in the testrig image, on the compose
# network, and copy its EmailableReport into the run folder. The exit code is the rig's: 0 no failing row, 1 a row
# failed (a conformance regression, or a stale benchmark entry), 2 the rig could not run.
#
#   bash testrigs/run-testrig.sh certify|verify --results FILE [--out DIR]   consume a runner's results.json
#   bash testrigs/run-testrig.sh certify|verify --invoke [--out DIR]         the rig starts the runner itself
#
# --results FILE   results.json below $HARNESS_RUN_DIR/reports (run-conformance.sh passes <run>/<component>/results.json)
# --invoke         the rig runs "inji-conformance run --component <c> --target <env.endpoint>" itself (invoke
#                  mode); Inji Verify's API is below /v1/verify, so its target is <env.endpoint>/v1/verify
# --out DIR        report folder (default $HARNESS_RUN_DIR/testrig/<module>-<UTC time>); report.txt there names the
#                  report file and its MinIO object key
#
# Upload: when the MinIO service of the reports profile is running, the rig's stock EmailableReport uploads the
# report to the bucket automationtests (s3-host http://minio:9000, user MINIO_ROOT_USER, password MINIO_ROOT_PASSWORD
# from $HARNESS_RUN_DIR/env.local). Otherwise upload is off. TESTRIG_IMAGE picks the image (default
# inji-conformance/testrig:local, built by "bash testrigs/build.sh --image"). TESTRIG_ENDPOINT overrides the rig's
# env.endpoint (default https://certify.inji.test:18450 or https://verify.inji.test:18451, the compose services).

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../scripts/lib/common.sh
source "$SCRIPT_DIR/../scripts/lib/common.sh"

readonly IMAGE=${TESTRIG_IMAGE:-inji-conformance/testrig:local}
readonly NETWORK=${HARNESS_COMPOSE_PROJECT}_default

usage() { sed -n '4,22p' "$0" | sed 's/^# \{0,1\}//'; }

component=${1:-}
case $component in
  certify) module=injicertify endpoint=${TESTRIG_ENDPOINT:-https://certify.inji.test:18450} api_path= ;;
  verify) module=injiverify endpoint=${TESTRIG_ENDPOINT:-https://verify.inji.test:18451} api_path=/v1/verify ;;
  -h | --help) usage && exit 0 ;;
  *) usage >&2 && exit 2 ;;
esac
shift
mode='' results='' out=''
while (($#)); do
  case $1 in
    --results)
      [[ -f ${2:-} ]] || die "--results: no such file: ${2:-}" 2
      mode=consume results=$(cd "$(dirname "$2")" && pwd)/$(basename "$2")
      shift 2
      ;;
    --invoke) mode=invoke && shift ;;
    --out) [[ -n ${2:-} ]] || die "--out needs a folder" 2; out=$2 && shift 2 ;;
    -h | --help) usage && exit 0 ;;
    *) die "unknown option: $1 (see --help)" 2 ;;
  esac
done
[[ -n $mode ]] || die "say where the results come from: --results FILE or --invoke" 2

harness_require_cmd docker "install Docker"
docker image inspect "$IMAGE" >/dev/null 2>&1 || die "image $IMAGE not found; build it with: bash testrigs/build.sh --image" 3
docker network inspect "$NETWORK" >/dev/null 2>&1 ||
  die "network $NETWORK not found; start the stack first: bash scripts/dc.sh --profile $component up -d --wait" 3

reports=$(harness_run_dir reports)
out=${out:-$(harness_run_dir testrig)/$module-$(date -u +%Y%m%dT%H%M%SZ)}
mkdir -p "$out"
out=$(cd "$out" && pwd)

java_props=(-Dmodules="$module" -Denv.user=inji-conformance -Denv.endpoint="$endpoint" -Denv.testLevel=smokeAndRegression
  -Dconformance.report.dir=/out)
mounts=(-v "$(harness_native_path "$out"):/out")
if [[ $mode == consume ]]; then
  [[ $results == "$reports"/* ]] || die "--results must be below $reports (it is mounted into the container)" 2
  mounts+=(-v "$(harness_native_path "$reports"):/reports:ro")
  java_props+=(-Dconformance.results.file="/reports/${results#"$reports"/}")
else
  mounts+=(-v "$(harness_native_path "$(harness_run_dir pki)"):/pki:ro" -v "$(harness_native_path "$reports"):/reports")
  # {target} is the rig's env.endpoint (ConformanceSettings), so the runner tests what the rig is configured for.
  java_props+=("-Dconformance.runner.command=inji-conformance run --component {component} --target {target}$api_path --out {out}"
    -Dconformance.runner.out="/reports/testrig-invoke-$component-$(date -u +%Y%m%dT%H%M%SZ)")
fi

env_args=(-e HARNESS_SUITE_URL=https://localhost.emobix.co.uk:18443 -e HARNESS_PKI_DIR=/pki -e HARNESS_REPORTS_DIR=/reports
  -e HARNESS_VERIFY_URL=https://verify.inji.test:18451/v1/verify -e HARNESS_CERTIFY_URL=https://certify.inji.test:18450)
minio_running=0
if [[ -n $(docker ps -q --filter "label=com.docker.compose.project=$HARNESS_COMPOSE_PROJECT" \
  --filter label=com.docker.compose.service=minio --filter status=running) ]]; then
  password=$(sed -n 's/^MINIO_ROOT_PASSWORD=//p' "$HARNESS_RUN_DIR/env.local" 2>/dev/null || true)
  [[ -n $password ]] || die "MinIO runs but MINIO_ROOT_PASSWORD is not in $HARNESS_RUN_DIR/env.local" 3
  minio_running=1
  # Upper-case names: the rig's ConformanceRigRunner reads them (RigRun.applyUploadSettings); a shell would drop
  # the hyphenated apitest-commons names.
  env_args+=(-e PUSH_REPORTS_TO_S3=yes -e S3_HOST=http://minio:9000 -e S3_ACCOUNT=automationtests
    -e S3_REGION=us-east-1 -e "S3_USER_KEY=${MINIO_ROOT_USER:-harness}" -e "S3_USER_SECRET=$password")
else
  env_args+=(-e PUSH_REPORTS_TO_S3=no)
  log_info "MinIO is not running: report upload off"
fi

log_info "testrig $module ($mode) in $IMAGE; report folder $out"
set +e
# shellcheck disable=SC2016 # "$@" and $(ls ...) are for the sh inside the container
harness_no_pathconv docker run --rm --network "$NETWORK" -u "$(harness_container_user)" -w "/home/$module" \
  "${mounts[@]}" "${env_args[@]}" "$IMAGE" \
  sh -c 'exec java "$@" -cp "$(ls /home/'"$module"'/apitest-'"$module"'-*-jar-with-dependencies.jar)" io.inji.testrig.apirig.'"$module"'.testrunner.ConformanceRigRunner' \
  sh "${java_props[@]}" >"$out/testrig.log" 2>&1
code=$?
set -e

report=$(find "$out" -maxdepth 1 -name "mosip-*-$module-conformance-*-full-report_*.html" -print | sort | tail -n 1)
{
  printf 'testrig %s exit code %s\n' "$module" "$code"
  if [[ -n $report ]]; then
    printf 'report %s\n' "$report"
    ((minio_running)) && printf 'minio  automationtests/%s/%s\n' "$module" "$(basename "$report")"
  else
    printf 'report none (see %s/testrig.log)\n' "$out"
  fi
} | tee "$out/report.txt"
exit "$code"
