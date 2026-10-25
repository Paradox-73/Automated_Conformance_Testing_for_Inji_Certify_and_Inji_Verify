# Configuration

Everything that can be set without editing code. Defaults reproduce the measured runs.

## Environment of the entry scripts

| Variable | Default | Meaning |
|---|---|---|
| `HARNESS_RUN_DIR` | `<repo>/run` | Run folder: `env.local`, `pki/`, `reports/`, `testrig/`, logs, the Python venv |
| `HARNESS_COMPOSE_PROJECT` | `inji-conformance` | Compose project name; must start with `inji-conformance` |
| `HARNESS_COMPOSE_FILES` | unset | Comma-separated compose override files, relative to the repository or absolute (for example `demo/regression.compose.yml`) |
| `HARNESS_TOOLS_DIR` | `$HARNESS_RUN_DIR/tools` | Extra tools in `<dir>/bin` (shellcheck, actionlint, mvn) |
| `HARNESS_CHECK_STRICT`, `CI` | `0`, unset | `1` / `true`: a missing tool is a check failure |
| `CERTIFY_AS_METADATA` | `add-authorization-endpoint` | What the TLS proxy does to Inji Certify's OAuth authorization server metadata. The default adds a placeholder `authorization_endpoint` and records a workaround in `results.json`; `as-is` serves the metadata unchanged. See [Inji Certify metadata workaround](#inji-certify-metadata-workaround) |
| `VERIFY_KEYSTORE_PATH`, `VERIFY_X509_SAN_DNS_HOST` | the pki-init keystore, `verify.inji.test` | Inji Verify's request signing keystore and its SAN |
| `TESTRIG_IMAGE` | `inji-conformance/testrig:local` | Image `testrigs/build.sh --image` builds and `run-testrig.sh` runs |
| `TESTRIG_MAVEN_ARGS` | empty | Extra Maven options for the jar stage of `testrigs/build.sh --image`, for example `-Dmaven.repo.remote=...`; `MAVEN_ARGS` applies to host builds only |
| `TESTRIG_ENDPOINT` | the compose service | `env.endpoint` of the rig in `run-testrig.sh`; in invoke mode the runner tests it |
| `MAVEN_ARGS` | unset | Extra Maven options for host builds of the testrigs and for `check.sh testrigs` |
| `CONFORMANCE_MAX_CONSECUTIVE_FAILURES` | `1000` (runner) | `run-test-plan.py`'s abort after modules in a row that did not finish |
| `PKI_FORCE` | unset | `1` makes `pki-init` write a new key set |
| `MINIO_ROOT_USER` | `harness` | MinIO user; its password `MINIO_ROOT_PASSWORD` is generated into `env.local` |
| `SMOKE_START_TIMEOUT`, `SMOKE_STATS_INTERVAL` | `420`, `3` | Seconds `compose/smoke.sh` waits for a healthy stack, and between memory samples |
| `OIDF_SUITE_CLONE`, `OIDF_SUITE_URL` | see [third_party/README.md](../third_party/README.md) | Where `bash third_party/reimport.sh verify` finds the upstream suite |
| `HARNESS_SUITE_URL`, `HARNESS_SUITE_MTLS_URL`, `HARNESS_VERIFY_URL`, `HARNESS_CERTIFY_URL`, `HARNESS_PKI_DIR`, `HARNESS_REPORTS_DIR` | set by the `runner` service | Where the runner finds the suite, Inji and the keys; only needed when running the runner outside Compose |

## Inji Certify metadata workaround

Inji Certify's OAuth authorization server metadata has no `authorization_endpoint`, and the suite stops every issuer
flow module without one ([finding](findings/certify-as-metadata-authorization-endpoint.md)). By default the TLS
proxy inserts a placeholder (`compose/tls-proxy/certify-as-metadata/add-authorization-endpoint.conf`) and marks the
response with the header `X-Harness-Shim`. The runner reads that header after the plan and records the change:

- `results.json` gets a `workarounds` entry with the name `certify-as-metadata-authorization-endpoint`, the finding
  and the setting that turns it off ([results schema](reference/results-schema.md));
- the runner's last line says `gate passed with 1 workaround: certify-as-metadata-authorization-endpoint`, after a
  line naming the finding and `CERTIFY_AS_METADATA=as-is`;
- `summary.html` shows a "Workarounds applied" box under the gate, the gate reads "Gate passed with 1 workaround",
  and `summary.md` lists the workaround under its heading.

To measure Inji Certify exactly as it publishes its metadata, set `CERTIFY_AS_METADATA=as-is` in `run/env.local`
or the environment and recreate the proxy. The proxy then serves `compose/tls-proxy/certify-as-metadata/as-is.conf`,
no workaround is recorded, and 13 of the 15 issuer modules end INTERRUPTED at `CheckServerConfiguration`, so the
gate fails. That run reproduces the finding; the default run measures everything after it.

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

| Port | Service | Open from the host |
|---|---|---|
| 18443 | conformance suite web page and API | `https://localhost.emobix.co.uk:18443` (self-signed certificate; the name is public DNS for 127.0.0.1) |
| 18444 | conformance suite mTLS listener | - |
| 18450, 18451 | Inji Certify and Inji Verify over TLS (`tls-proxy`; `https://certify.inji.test:18450`, `https://verify.inji.test:18451/v1/verify` inside the network) | only through containers |
| 18460, 18461 | Inji Certify and Inji Verify over plain HTTP, for debugging | `http://127.0.0.1:18461/v1/verify/...` |
| 18900, 18901 | MinIO S3 API and web console | `http://127.0.0.1:18901`, user `harness`, password `MINIO_ROOT_PASSWORD` from `env.local` |

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
