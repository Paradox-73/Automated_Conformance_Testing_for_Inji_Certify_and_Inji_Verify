# Configuration

Everything that can be set without editing code. Defaults reproduce the measured runs.

## Environment of the entry scripts

| Variable | Default | Meaning |
|---|---|---|
| `HARNESS_RUN_DIR` | `<repo>/run` | Run folder: `env.local`, `pki/`, `reports/`, `testrig/`, logs, the Python venv |
| `HARNESS_COMPOSE_PROJECT` | `ps01-harness` | Compose project name; must start with `ps01-` |
| `HARNESS_COMPOSE_FILES` | unset | Comma-separated compose override files, relative to the repository or absolute (for example `demo/regression.compose.yml`) |
| `HARNESS_TOOLS_DIR` | `$HARNESS_RUN_DIR/tools` | Extra tools in `<dir>/bin` (shellcheck, actionlint, mvn) |
| `HARNESS_CHECK_STRICT`, `CI` | `0`, unset | `1` / `true`: a missing tool is a check failure |
| `CERTIFY_AS_METADATA` | `add-authorization-endpoint` | `as-is` serves Inji Certify's OAuth metadata unchanged ([finding](findings/certify-as-metadata-authorization-endpoint.md)) |
| `VERIFY_KEYSTORE_PATH`, `VERIFY_X509_SAN_DNS_HOST` | the pki-init keystore, `verify.inji.test` | Inji Verify's request signing keystore and its SAN |
| `TESTRIG_IMAGE` | `ps01-harness/testrig:local` | Image `testrigs/build.sh --image` builds and `run-testrig.sh` runs |
| `MAVEN_ARGS` | unset | Extra Maven options for the testrig build and check |
| `CONFORMANCE_MAX_CONSECUTIVE_FAILURES` | `1000` (runner) | `run-test-plan.py`'s abort after modules in a row that did not finish |

## Images

Every image is pinned by digest in `docker-compose.yml`; each can be replaced from the environment or `env.local`,
for example to test a new Inji build:

| Variable | Default |
|---|---|
| `CERTIFY_IMAGE` | `injistackqa/inji-certify-with-plugins:1.0.x@sha256:2c72a78c...` |
| `VERIFY_IMAGE` | `injistackqa/inji-verify-service:1.0.x@sha256:a9b81fd4...` |
| `SUITE_SERVER_IMAGE`, `SUITE_NGINX_IMAGE`, `SUITE_MONGODB_IMAGE` | conformance suite release-v5.3.1 |
| `CERTIFY_DB_IMAGE`, `VERIFY_DB_IMAGE`, `TLS_PROXY_IMAGE`, `PKI_IMAGE`, `PROBE_IMAGE`, `MINIO_IMAGE`, `MINIO_MC_IMAGE`, `RUNNER_IMAGE` | see `docker-compose.yml` |

The run manifest records the image and digest each service ran with.

## Generated secrets

`scripts/dc.sh` writes `$HARNESS_RUN_DIR/env.local` on first use with random values for `VERIFY_DB_PASSWORD`,
`CERTIFY_DB_PASSWORD`, `CERTIFY_KEYSTORE_PASSWORD`, `MINIO_ROOT_PASSWORD` and `VERIFY_KEYSTORE_PASSWORD`. It is never
committed. Certify's keystore volume, its database volume and `env.local` belong together: remove all three
(`bash scripts/dc.sh --profile '*' down -v` and delete the file) or none. `pki-init` writes the test PKI into
`$HARNESS_RUN_DIR/pki` and reuses it while the CA is valid for 30 more days (`PKI_FORCE=1` makes a new set).

## Ports

All bound to 127.0.0.1; preflight checks them and names what holds a busy one.

| Port | Service |
|---|---|
| 18443, 18444 | conformance suite (web and API; mTLS listener) |
| 18450, 18451 | Inji Certify and Inji Verify over TLS (`tls-proxy`) |
| 18460, 18461 | Inji Certify and Inji Verify over plain HTTP, for debugging |
| 18900, 18901 | MinIO S3 API and console |

## Plan templates

`conformance/plans/<component>.<name>.json` ([format](../conformance/plans/README.md)). The runner picks the one
template per component and track that is not marked `"alternative": true`; `--template NAME` picks another.

| Template | Track | Plan and variant |
|---|---|---|
| `certify.oid4vci-1_0-issuer` | gate | `oid4vci-1_0-issuer-test-plan`: vci, sd_jwt_vc, pre-authorized code, issuer initiated, private_key_jwt, dpop (`--variant sender_constrain=mtls` reaches the same conditions, measured 2026-10-14) |
| `verify.oid4vp-1final-verifier` | gate | `oid4vp-1final-verifier-test-plan`: plain_vp, sd_jwt_vc, redirect_uri, url_query, direct_post |
| `verify.oid4vp-1final-verifier-x509-san-dns` | gate, alternative | the same plan with x509_san_dns and request_uri_signed |
| `certify.oid4vci-1_0-issuer-haip`, `verify.oid4vp-1final-verifier-haip` | haip | the HAIP plans, never gating |

The runner image copies `conformance/`: after changing a template or the benchmark, rebuild it with
`bash scripts/dc.sh --profile tools build runner` (or `./run-full-stack-conformance.sh --prepare-only`).
