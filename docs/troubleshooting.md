# Troubleshooting

Symptom, cause, fix. Setup and Windows-specific problems are also in
[CONTRIBUTING.md](../CONTRIBUTING.md#troubleshooting).

| Symptom | Cause and fix |
|---|---|
| `preflight: ports in use on 127.0.0.1: 18451 (...)`, exit 3 | Another program holds a harness port. Find it with `lsof -iTCP -sTCP:LISTEN` (macOS), `ss -ltnp` (Linux) or `netstat -ano` (Windows) and stop it. |
| `preflight: containers of ps01-harness already exist` | An earlier run with `--keep-stack`, or one that was killed. `bash scripts/dc.sh --profile '*' down -v`. |
| `the stack did not become healthy`, exit 3 | Read `<run>/logs/compose-up.log` and `logs/compose.log`. Inji Certify needs about 2 minutes on a loaded machine; Docker needs at least 4 GiB. |
| `expected one haip plan template ... found none` (or any change to `conformance/` seems ignored) | The runner image is older than the checkout. `bash scripts/dc.sh --profile tools build runner`. |
| Every issuer flow module INTERRUPTED at `CheckServerConfiguration` "Couldn't find required component: authorization_endpoint" | `CERTIFY_AS_METADATA=as-is` is set: Inji Certify publishes no `authorization_endpoint`. Unset it to let the proxy add one ([finding](findings/certify-as-metadata-authorization-endpoint.md)). |
| A plan stops after three modules with "conformance server appears to be unhealthy" | `run-test-plan.py`'s circuit breaker. The runner sets `CONFORMANCE_MAX_CONSECUTIVE_FAILURES=1000`; set it yourself when calling the script directly. |
| Every x509_san_dns verifier module fails `ValidateRequestObjectSignatureAgainstX5cHeader` | Expected with that configuration ([suite-limitations.md](suite-limitations.md)); the default template uses `redirect_uri`. With "Leaf certificate ... must not be self-signed", Inji Verify uses its bundled keystore: check `VERIFY_KEYSTORE_PATH`. |
| A REVIEW module is a regression "Inji Verify's verdict could not be read" | The evidence upload never happened: Inji Verify did not answer `GET /vp-result` (stopped, or the transaction expired). See `logs/handoffs.jsonl`. |
| `run exit 2` with "cross-check failed" | The gate and `run-test-plan.py` disagree on the same benchmark files: a bug in the runner or a benchmark entry the two read differently. Report it with the run folder. |
| `run exit 2` with "benchmark entries that match no module" | An entry's test name, file name pattern or variant matches no module of the plan; fix or remove it. |
| `inji-conformance run` exits 4 | `--timeout-minutes` (default 30) reached; `results.json` is still written, unfinished modules are regressions. |
| `testrig ... exit code 2` | The rig could not run; read `<out>/testrig.log`. `image ps01-harness/testrig:local not found`: `bash testrigs/build.sh --image`. |
| Rig report not in MinIO | The reports profile was not running (`run-testrig.sh` prints "MinIO is not running: report upload off"), or the rig image is older than 2026-10-14 (no `applyUploadSettings`). |
| `testrigs/build.sh`: "Could not create local repository at /var/maven/.m2/repository" | An old build script and a root-owned cache volume. Current `build.sh` hands the volume to the calling user; or `docker volume rm ps01-harness-m2`. |
| Inji Certify returns HTTP 200 but nothing happened | Its admin APIs report errors as HTTP 200 with an `errors` list; read the body. |
| GitHub Actions: "The job was not started because recent account payments have failed..." | Billing of the repository owner's account ([ci.md](ci.md#status-of-the-real-runs)). |
