#!/bin/sh
# minio-init: create the bucket the api-testrigs upload their reports to. Runs inside the minio container as its
# post-start hook (docker-compose.yml), so it uses the mc client of that image and the alias "local" that
# MC_HOST_local defines. Idempotent: an existing bucket and its objects are kept.
#
# Environment: MINIO_BUCKET (bucket name, default automationtests), MC_HOST_local (set by docker-compose.yml),
# MINIO_INIT_TIMEOUT (seconds to wait for the server, default 60).
set -eu

bucket=${MINIO_BUCKET:-automationtests}
timeout=${MINIO_INIT_TIMEOUT:-60}

# The hook starts together with the server process; wait until the S3 API accepts requests.
waited=0
until mc ready local >/dev/null 2>&1; do
  waited=$((waited + 1))
  if [ "$waited" -ge "$timeout" ]; then
    echo "minio-init: server not ready after ${timeout}s" >&2
    exit 1
  fi
  sleep 1
done

mc mb --ignore-existing "local/$bucket"
echo "minio-init: bucket $bucket ready"
