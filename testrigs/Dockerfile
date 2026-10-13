# Testrig image: both Inji api-testrigs with their conformance suites, and the inji-conformance runner for invoke mode.
# Built from the repository root after "bash testrigs/build.sh" made the two shaded jars:
#
#   docker build -f testrigs/Dockerfile -t ps01-harness/testrig:local .
#
# Layout, as the rigs' stock images and RigRun.suiteFile expect (working directory /home/<module>):
#   /home/injicertify/apitest-injicertify-*-jar-with-dependencies.jar, /home/injicertify/testNgXmlFiles/
#   /home/injiverify/apitest-injiverify-*-jar-with-dependencies.jar,   /home/injiverify/testNgXmlFiles/
#   /opt/harness (runner package in /opt/harness/venv, third_party/, conformance/)
# testrigs/run-testrig.sh starts it on the compose network as the calling user; the rigs extract their resources
# next to the jar, so both folders are writable by any user. Nothing is written outside the container except the
# report folder mounted at /out.
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

COPY testrigs/inji-certify-api-test/target/apitest-injicertify-*-jar-with-dependencies.jar /home/injicertify/
COPY testrigs/inji-certify-api-test/testNgXmlFiles /home/injicertify/testNgXmlFiles
COPY testrigs/inji-verify-api-test/target/apitest-injiverify-*-jar-with-dependencies.jar /home/injiverify/
COPY testrigs/inji-verify-api-test/testNgXmlFiles /home/injiverify/testNgXmlFiles
RUN chmod 1777 /home/injicertify /home/injiverify

ENV PATH=/opt/harness/venv/bin:$PATH \
    INJI_CONFORMANCE_HOME=/opt/harness \
    INJI_CONFORMANCE_SCHEMA_DIR=/opt/harness/conformance/schema \
    HOME=/tmp

USER 1000:1000
WORKDIR /home/injicertify
CMD ["java", "-version"]
