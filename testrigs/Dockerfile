# Testrig image: both Inji api-testrigs with their conformance suites, and the inji-conformance runner for invoke mode.
# Built from the repository root; the first stage compiles the two shaded jars from the sources, so the host needs
# neither a JDK nor Maven:
#
#   docker build -f testrigs/Dockerfile -t inji-conformance/testrig:local .     (or: bash testrigs/build.sh --image)
#
# Layout, as the rigs' stock images and RigRun.suiteFile expect (working directory /home/<module>):
#   /home/injicertify/apitest-injicertify-*-jar-with-dependencies.jar, /home/injicertify/testNgXmlFiles/
#   /home/injiverify/apitest-injiverify-*-jar-with-dependencies.jar,   /home/injiverify/testNgXmlFiles/
#   /opt/harness (runner package in /opt/harness/venv, third_party/, conformance/)
# testrigs/run-testrig.sh starts it on the compose network as the compose services' user; the rigs extract their
# resources next to the jar, so both folders are writable by any user. Nothing is written outside the container
# except the report folder mounted at /out.

# Stage 1: the jars. The Maven repository lives in a BuildKit cache mount, so a rebuild downloads nothing new.
# Tests, javadoc and source jars are left out here; "bash scripts/check.sh testrigs" runs the bridge tests.
FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS jars
# Extra Maven options for this stage, for example a mirror (build.sh passes TESTRIG_MAVEN_ARGS); Maven 3.9 reads them.
ARG MAVEN_ARGS=""
WORKDIR /src
COPY testrigs testrigs
RUN --mount=type=cache,target=/root/.m2 \
    mvn -B -ntp -f testrigs/pom.xml -pl apitest-commons-conformance,inji-verify-api-test,inji-certify-api-test -am \
      package -DskipTests -Dgpg.skip=true -Dmaven.gitcommitid.skip=true -Dmaven.javadoc.skip=true -Dmaven.source.skip=true \
    && mkdir /jars \
    && cp testrigs/inji-certify-api-test/target/apitest-injicertify-*-jar-with-dependencies.jar \
      testrigs/inji-verify-api-test/target/apitest-injiverify-*-jar-with-dependencies.jar /jars/

# Stage 2: the image.
FROM eclipse-temurin:21.0.8_9-jre-noble@sha256:20e7f7288e1c18eebe8f06a442c9f7183342d9b022d3b9a9677cae2b558ddddd

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/harness
COPY runner/pyproject.toml runner/README.md runner/
COPY runner/src runner/src
RUN python3 -m venv /opt/harness/venv \
    && /opt/harness/venv/bin/pip install --no-compile ./runner \
    && rm -rf runner/build
COPY third_party/oidf-conformance-suite third_party/oidf-conformance-suite
COPY conformance conformance

COPY --from=jars /jars/apitest-injicertify-*-jar-with-dependencies.jar /home/injicertify/
COPY testrigs/inji-certify-api-test/testNgXmlFiles /home/injicertify/testNgXmlFiles
COPY --from=jars /jars/apitest-injiverify-*-jar-with-dependencies.jar /home/injiverify/
COPY testrigs/inji-verify-api-test/testNgXmlFiles /home/injiverify/testNgXmlFiles
RUN chmod 1777 /home/injicertify /home/injiverify

ENV PATH=/opt/harness/venv/bin:$PATH \
    INJI_CONFORMANCE_HOME=/opt/harness \
    INJI_CONFORMANCE_SCHEMA_DIR=/opt/harness/conformance/schema \
    HOME=/tmp

USER 1000:1000
WORKDIR /home/injicertify
CMD ["java", "-version"]
