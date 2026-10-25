# Image of the inji-conformance runner: the Python package, the conformance suite's scripts (vendored unchanged)
# and the plan templates and schemas. Built from the repository root (compose service "runner"):
#
#   bash scripts/dc.sh --profile tools build runner
#
# Runs as the calling user (compose sets user:), writes only below the folder given with --out.
FROM python:3.12.15-slim@sha256:29113dcae7aad06daa8e95260fa09f27d62be33b9687ea3774f771d601a02256

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/harness

# Dependencies and package first, so a change to plans or schemas does not reinstall them.
COPY runner/pyproject.toml runner/README.md runner/constraints.txt runner/
COPY runner/src runner/src
RUN pip install --no-compile -c runner/constraints.txt ./runner \
    && rm -rf runner/build

COPY third_party/oidf-conformance-suite third_party/oidf-conformance-suite
COPY conformance conformance

# Where the package finds the vendored scripts, the plan templates and the JSON Schemas.
ENV INJI_CONFORMANCE_HOME=/opt/harness \
    INJI_CONFORMANCE_SCHEMA_DIR=/opt/harness/conformance/schema

USER 1000:1000
WORKDIR /tmp
CMD ["inji-conformance", "--help"]
