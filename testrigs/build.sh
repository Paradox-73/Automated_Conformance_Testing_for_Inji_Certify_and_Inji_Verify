#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
#
# Build the testrig image, or the two Inji api-testrig jars with the conformance bridge on the host.
#
#   bash testrigs/build.sh --image    the image ps01-harness/testrig:local (TESTRIG_IMAGE overrides); the jars are
#                                     compiled inside the image build, so only Docker is needed (any OS)
#   bash testrigs/build.sh            the jars on the host: testrigs/inji-*-api-test/target/apitest-inji*-jar-with-dependencies.jar
#
# Host jars use the host's Maven when it runs on JDK 21 or newer (the rigs compile for release 21), else the
# maven:3.9-eclipse-temurin-21 image with the checkout bind-mounted and a named volume as the Maven repository
# (ps01-harness-m2). That container path is slow on Windows and macOS bind mounts; prefer --image there. MAVEN_ARGS
# adds options to host builds, for example a settings file with a mirror.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=../scripts/lib/common.sh
source "$SCRIPT_DIR/../scripts/lib/common.sh"

readonly MAVEN_IMAGE=maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237
readonly MODULES=apitest-commons-conformance,inji-verify-api-test,inji-certify-api-test
readonly IMAGE=${TESTRIG_IMAGE:-ps01-harness/testrig:local}

image=0
case ${1:-} in
  '') ;;
  --image) image=1 ;;
  -h | --help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//' && exit 0 ;;
  *) die "unknown option: $1 (use --image or --help)" 2 ;;
esac

host_maven_ok() {
  local mvn java_version
  mvn=$(harness_find_tool mvn) || return 1
  java_version=$("$mvn" -v 2>/dev/null | sed -n 's/^Java version: \([0-9]*\).*/\1/p')
  [[ $java_version =~ ^[0-9]+$ ]] && ((java_version >= 21))
}

started=$(date -u +%s)
cd "$HARNESS_ROOT"
if ((image)); then
  harness_require_cmd docker "install Docker"
  log_info "building the image $IMAGE (the jars are compiled in its first stage)"
  docker build -f testrigs/Dockerfile -t "$IMAGE" .
  log_info "image built in $(($(date -u +%s) - started)) s"
  exit 0
fi

args=(-B -f testrigs/pom.xml -pl "$MODULES" -am package -Dgpg.skip=true -Dmaven.gitcommitid.skip=true)
# shellcheck disable=SC2206 # MAVEN_ARGS is a list of options by design
[[ -n ${MAVEN_ARGS:-} ]] && args+=($MAVEN_ARGS)

if host_maven_ok; then
  log_info "building with the host's Maven: mvn ${args[*]}"
  "$(harness_find_tool mvn)" "${args[@]}"
else
  harness_require_cmd docker "install JDK 21 and Maven 3.9, or Docker"
  log_info "no Maven on JDK 21 or newer on the host: building in $MAVEN_IMAGE"
  # A new named volume belongs to root; hand it to the calling user, who runs the build.
  harness_no_pathconv docker run --rm -u 0 -v ps01-harness-m2:/var/maven/.m2 "$MAVEN_IMAGE" \
    chown "$(id -u):$(id -g)" /var/maven/.m2
  harness_no_pathconv docker run --rm -u "$(id -u):$(id -g)" -e MAVEN_CONFIG=/var/maven/.m2 \
    -v ps01-harness-m2:/var/maven/.m2 -v "$(harness_native_path "$HARNESS_ROOT"):/src" -w /src \
    "$MAVEN_IMAGE" mvn -Duser.home=/var/maven "${args[@]}"
fi
for jar in testrigs/inji-certify-api-test/target/apitest-injicertify-*-jar-with-dependencies.jar \
  testrigs/inji-verify-api-test/target/apitest-injiverify-*-jar-with-dependencies.jar; do
  [[ -f $jar ]] || die "expected jar missing after the build: $jar"
  log_info "jar: $jar ($(du -h "$jar" | cut -f1))"
done
log_info "jars built in $(($(date -u +%s) - started)) s"

