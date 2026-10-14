# Troubleshooting

Symptom, cause, fix. The first table covers runs; the second covers setting up a machine and working on the
harness.

## Runs

| Symptom | Cause and fix |
|---|---|
| `preflight: ports in use on 127.0.0.1: 18451 (...)`, exit 3 | Another program holds a harness port. Find it with `lsof -iTCP -sTCP:LISTEN` (macOS), `ss -ltnp` (Linux) or `netstat -ano` (Windows) and stop it. |
| `preflight: containers of ps01-harness already exist` | An earlier run with `--keep-stack`, or one that was killed. `bash scripts/dc.sh --profile '*' down -v`. |
| `the stack did not become healthy`, exit 3 | Read `<run>/logs/compose-up.log` and `logs/compose.log`. Inji Certify needs about 2 minutes on a loaded machine; Docker needs at least 4 GiB. |
| `inji-conformance run` exits 3 | The suite or the Inji component did not answer within 120 s, or a key from `pki-init` is missing. Start the stack with `up -d --wait` first. |
| `expected one haip plan template ... found none` (or any change to `conformance/` seems ignored) | The runner image copies `conformance/` and is older than the checkout. `bash scripts/dc.sh --profile tools build runner`. |
| Every issuer flow module INTERRUPTED at `CheckServerConfiguration` "Couldn't find required component: authorization_endpoint" | `CERTIFY_AS_METADATA=as-is` is set: Inji Certify publishes no `authorization_endpoint`. Unset it to let the proxy add one ([finding](findings/certify-as-metadata-authorization-endpoint.md)). |
| A plan stops after three modules with "conformance server appears to be unhealthy" | `run-test-plan.py`'s circuit breaker. The runner sets `CONFORMANCE_MAX_CONSECUTIVE_FAILURES=1000`; set it yourself when calling the script directly. |
| Every x509_san_dns verifier module fails `ValidateRequestObjectSignatureAgainstX5cHeader` | Expected with that configuration ([suite-limitations.md](suite-limitations.md)); the default template uses `redirect_uri`. With "Leaf certificate ... must not be self-signed", Inji Verify uses its bundled keystore: check `VERIFY_KEYSTORE_PATH`. |
| Verifier modules fail at the wallet's response with HTTP 500 from Inji Verify | The Verify database was created before `compose/verify/init.sql` gained the `vp_submission` response code columns (2026-10-07). The database has no volume, so `bash scripts/dc.sh --profile '*' down -v` and a new `up` recreate it. |
| A REVIEW module is a regression "Inji Verify's verdict could not be read" | The evidence upload never happened: Inji Verify did not answer `GET /vp-result` (stopped, or the transaction expired). See `logs/handoffs.jsonl`. |
| `run exit 2` with "cross-check failed" | The gate and `run-test-plan.py` disagree on the same benchmark files: a bug in the runner or a benchmark entry the two read differently. Report it with the run folder. |
| `run exit 2` with "benchmark entries that match no module" | An entry's test name, file name pattern or variant matches no module of the plan; fix or remove it. |
| `inji-conformance run` exits 4 | `--timeout-minutes` (default 30) reached; `results.json` is still written, unfinished modules are regressions. Free Docker resources or raise the limit. |
| `testrig ... exit code 2` | The rig could not run; read `<out>/testrig.log`. `image ps01-harness/testrig:local not found`: `bash testrigs/build.sh --image`. |
| Rig report not in MinIO | The reports profile was not running (`run-testrig.sh` prints "MinIO is not running: report upload off"), or the rig image is older than 2026-10-14 (no `applyUploadSettings`). |
| A rig report has no conformance rows | `EmailableReport` leaves out suites whose name contains "Master Suite"; the rows must be in the child suite. |
| A rig report lands in the wrong place or is missing (Windows) | TestNG's output folder is relative to the working directory: keep `conformance.report.dir` on the same drive as the working directory. |
| Inji Certify returns HTTP 200 but nothing happened | Its admin APIs report errors as HTTP 200 with an `errors` list; read the body. |
| GitHub Actions: "The job was not started because recent account payments have failed..." | Billing of the repository owner's account ([ci.md](ci.md#status-of-the-real-runs)). |

## Setup and the stack

| Symptom | Cause and fix |
|---|---|
| `Filename too long` during clone or checkout (Windows) | Long paths in the imported testrigs. Clone with `git -c core.longpaths=true clone ...` and run `git config core.longpaths true`. |
| `check.sh eol` fails on a file you wrote | The editor saved CRLF. Use an editor that honours `.editorconfig`, or convert the file to LF. |
| An imported upstream file no longer matches upstream | It was copied from a working tree that Git for Windows converted to CRLF. Re-extract with `git -c core.autocrlf=false archive` or `git cat-file blob`. |
| A check prints `SKIP ... not found` | The tool is missing. Install it or put it in `$HARNESS_TOOLS_DIR/bin`. With `CI=true` or `--strict` it is a FAIL. |
| `python3` opens the Microsoft Store or prints a hint (Windows) | The Store placeholder. Install Python from python.org and turn off the App execution aliases for `python.exe` and `python3.exe` in Windows settings. |
| `inji-conformance.exe`: "Permission denied" right after install (Windows with Smart App Control) | Reinstall the launcher: `"$HARNESS_RUN_DIR/venv/Scripts/python" -m pip install --force-reinstall --no-deps --editable ./runner`. This fixed it on 2026-10-04. |
| `VERIFY_DB_PASSWORD` error from `docker compose` | Compose was called directly. Use `bash scripts/dc.sh`. |
| Bind mounts empty or wrong on Windows | Call through `dc.sh` (it passes native paths and turns off Git Bash path rewriting). |
| `up --wait` fails because a one-shot container exited | Compose (5.5.1, measured) fails `--wait` when a one-shot container that nothing depends on has exited. That is why `pki-init` is only in the `verify`, `certify` and `tools` profiles and MinIO's bucket is created by a `post_start` hook; keep new one-shot steps the same way. |
| `localhost.emobix.co.uk` does not resolve | The name is public DNS for 127.0.0.1. Offline, add `127.0.0.1 localhost.emobix.co.uk` to the hosts file, or use `curl --resolve localhost.emobix.co.uk:18443:127.0.0.1`. |
| `verify.inji.test` or `certify.inji.test` does not resolve on the host | Expected: those names exist only inside the Compose network. Use the `probe` or `runner` container, for example `bash scripts/dc.sh run --rm probe --cacert /pki/ca.crt https://verify.inji.test:18451/v1/verify/actuator/health`, or `http://127.0.0.1:18461/v1/verify/...` for debugging. |
| `suite-server` never healthy; its log says "A non-https request has been received" | Something called the server without `X-Forwarded-Proto: https`. Go through `https://localhost.emobix.co.uk:18443`. |
| Inji Certify not healthy within the start limit | It needs about 2 minutes on a loaded machine. Read `bash scripts/dc.sh --profile certify logs certify`; raise `SMOKE_START_TIMEOUT` if it is only slow. |
| Inji Certify or Verify fails to start, sign or log in to its database after `env.local` or one volume was deleted | The keystore volume, the database volume and the passwords in `env.local` belong together: `bash scripts/dc.sh --profile '*' down -v` and start again. |
| The smoke test's `certify` check shows a `credential_issuer` other than `https://certify.inji.test:18450` | `CERTIFY_IMAGE` points at an image that ignores the mounted configuration, or the properties were edited; see [compose/certify/README.md](../compose/certify/README.md). |
| `minio` unhealthy, log says the bucket is missing | `compose/minio/init.sh` could not reach the server within 60 s. `bash scripts/dc.sh --profile reports logs minio` shows the hook's output. |
| `pull access denied` for `minio/minio` or `minio/mc` | Those images are no longer published; the defaults use the `pgsty` builds. Point `MINIO_IMAGE` / `MINIO_MC_IMAGE` at a build you can pull. |
| `testrigs/build.sh`: "Could not create local repository at /var/maven/.m2/repository" | An old build script and a root-owned cache volume. Current `build.sh` hands the volume to the calling user; or `docker volume rm ps01-harness-m2`. |
| First Maven build of a testrig takes 8-15 minutes | Downloads, and the rig pom declares a snapshots repository that Maven probes for every artifact. Keep `~/.m2`; pass a mirror through `MAVEN_ARGS` (host builds) or `TESTRIG_MAVEN_ARGS` (image builds). |
