# compose

Assets for the root [`docker-compose.yml`](../docker-compose.yml): one Docker Compose project (`inji-conformance`) that
runs the OpenID Foundation conformance suite and the Inji systems under test side by side.

## Quick start

```bash
bash scripts/dc.sh --profile verify pull                # once; about 1.1 GB to download (compressed)
bash scripts/dc.sh --profile verify up -d --wait        # suite + Inji Verify + TLS proxy, healthy in about 1 minute
bash scripts/dc.sh --profile verify down -v             # stop and delete containers, network and volumes
bash compose/smoke.sh verify                            # start, check, measure, remove (exit 0 when all checks pass)

bash scripts/dc.sh --profile certify --profile reports pull   # once; Inji Certify is about 0.9 GB compressed
bash compose/smoke.sh certify reports                   # suite + Inji Certify + TLS proxy + MinIO
```

Always call Compose through [`scripts/dc.sh`](../scripts/dc.sh); a plain `docker compose` lacks the generated
passwords and, on Windows, the path conversion. Arguments go to `docker compose` unchanged.

| What `dc.sh` adds | Why |
|---|---|
| `--project-name inji-conformance --file <repo>/docker-compose.yml` | Works from any folder. `HARNESS_COMPOSE_PROJECT` overrides the name; it must start with `inji-conformance`. |
| `--env-file $HARNESS_RUN_DIR/env.local` | Created on first use with random passwords (32 hex characters each); later calls only append names that are missing, so a database keeps the password it was created with. Never in git. Delete it together with the volumes to get new passwords. |
| Creates `$HARNESS_RUN_DIR/pki` and `$HARNESS_RUN_DIR/reports` | They are bind-mounted; created as the calling user so containers that run as that user can write them on Linux. |
| `HARNESS_RUN_DIR` as a native path, Git Bash path rewriting off | Bind mounts work from Git Bash on Windows. |
| `HARNESS_UID`, `HARNESS_GID` | `pki-init` and `runner` run as the calling user, so files they write in the run folder stay deletable on Linux. |

`HARNESS_RUN_DIR` defaults to `<repo>/run` (ignored by git).

## Profiles and services

| Profile | Services started |
|---|---|
| `suite` | `suite-mongodb`, `suite-server`, `suite-nginx` |
| `verify` | the suite, `verify-db`, `verify-service`, `pki-init`, `tls-proxy` |
| `certify` | the suite, `certify-db`, `certify`, `pki-init`, `tls-proxy` |
| `reports` | `minio` (S3 store with the `automationtests` bucket for the testrig reports) |
| `tools` | one-off containers for `dc.sh run --rm`: `runner` (built from `runner/`), `probe` (curl), `minio-mc` (S3 client), `pki-init` |

| Service | Image (default, pinned by tag and digest) | Override | Host port (127.0.0.1 only) | Name inside the network | Memory limit |
|---|---|---|---|---|---|
| `suite-server` | `registry.gitlab.com/openid/conformance-suite:release-v5.3.1` | `SUITE_SERVER_IMAGE` | none | - | 1536 MiB |
| `suite-nginx` | `registry.gitlab.com/openid/conformance-suite/nginx:release-v5.3.1` + [`suite/nginx.conf`](suite/nginx.conf) | `SUITE_NGINX_IMAGE` | 18443, 18444 | `localhost.emobix.co.uk` | 128 MiB |
| `suite-mongodb` | `mongo:6.0.13`, named volume `suite-mongodb-data` | `SUITE_MONGODB_IMAGE` | none | - | 512 MiB |
| `verify-service` | `injistackqa/inji-verify-service:1.0.x` (commit `ad3595f`) | `VERIFY_IMAGE` | 18461 (plain HTTP, debugging only) | - | 768 MiB |
| `verify-db` | `postgres:13` + [`verify/init.sql`](verify/init.sql) | `VERIFY_DB_IMAGE` | none | - | 256 MiB |
| `certify` | `injistackqa/inji-certify-with-plugins:1.0.x` (commit `bbd913e`, `release-1.0.x`) + [`certify/config/`](certify/README.md) | `CERTIFY_IMAGE` | 18460 (plain HTTP, debugging only) | - | 1 GiB |
| `certify-db` | `postgres:15` + [`certify/certify_init.sql`](certify/certify_init.sql), named volume `certify-db-data` | `CERTIFY_DB_IMAGE` | none | - | 256 MiB |
| `tls-proxy` | `nginx:1.30.5-alpine` + [`tls-proxy/`](tls-proxy/) | `TLS_PROXY_IMAGE` | 18450, 18451 | `verify.inji.test`, `certify.inji.test` | 128 MiB |
| `minio` | `pgsty/minio:RELEASE.2026-08-04T00-00-00Z` + [`minio/init.sh`](minio/README.md), named volume `minio-data` | `MINIO_IMAGE` | 18900 (S3), 18901 (console) | `minio` | 512 MiB |
| `minio-mc` | `pgsty/mc:RELEASE.2026-09-16T00-00-00Z` | `MINIO_MC_IMAGE` | none | - | 128 MiB |
| `pki-init` | `python:3.12.15-slim` + [`pki/generate.py`](pki/generate.py) | `PKI_IMAGE` | none (no network) | - | 128 MiB |
| `runner` | built from `runner/Dockerfile` (added by the runner lane) | `RUNNER_IMAGE` | none | - | 512 MiB |
| `probe` | `curlimages/curl:8.22.0` | `PROBE_IMAGE` | none | - | 64 MiB |

- Overrides are read from the environment or from `env.local`, for example
  `VERIFY_IMAGE=injistackqa/inji-verify-service:develop bash compose/smoke.sh verify`. The digests in
  `docker-compose.yml` make the default run reproducible; `bash scripts/dc.sh --profile '*' config --images` lists
  them.
- Every long-running service has a healthcheck, so `up --wait` returns only when the stack can take a test run.
- Containers log to Docker's json-file driver, capped at 3 files of 1 MB per container.

### Why these names and ports

- The suite builds every URL it hands out (test endpoints, `authorization_endpoint`, log links) from `BASE_URL`
  `https://localhost.emobix.co.uk:18443`. Its nginx therefore listens on 18443 inside the network too, and carries
  the network alias `localhost.emobix.co.uk`. On a host the same public DNS name resolves to 127.0.0.1, so one URL
  works for a browser on the host and for containers. Port 18444 is the suite's mTLS listener
  (`BASE_MTLS_URL`).
- The suite rejects plain-http `request_uri`, `response_uri` and issuer URLs, so Inji Verify sits behind
  `tls-proxy` as `https://verify.inji.test:18451`. `INJI_VP_SUBMISSION_BASE_URL` points there, so the
  `request_uri` and `response_uri` that Verify puts into its request objects are reachable by the suite, which
  plays the wallet. `.test` names exist only inside the compose network (`.test` is reserved for testing), so
  everything that calls them runs in a container on that network (`runner`, `probe`, the testrigs).
- Verify signs request objects with an Ed25519 key whose certificate the run's test CA issued for
  `verify.inji.test` (`pki-init`, `verify-request-signing.p12`, password `VERIFY_KEYSTORE_PASSWORD` in `env.local`),
  so the `x509_san_dns` client id is `x509_san_dns:verify.inji.test`. Until 2026-10-14 it used the keystore bundled
  in its image (SAN `test.example.com`), whose self-signed certificate the suite rejects. For `x509_san_dns` the
  suite checks the client id against that certificate, not against the `response_uri` host.
- `tls-proxy` serves only the RFC 9325 TLS 1.2 cipher suites, and by default adds a placeholder
  `authorization_endpoint` to Inji Certify's OAuth metadata (`CERTIFY_AS_METADATA`, see
  [docs/findings/certify-as-metadata-authorization-endpoint.md](../docs/findings/certify-as-metadata-authorization-endpoint.md)).
- Inji Certify sits behind `tls-proxy` as `https://certify.inji.test:18450`, which is also its
  `mosip.certify.domain.url`. The domain has no path, so the issuer identifier is the origin and OpenID4VCI 1.0
  puts the metadata at `/.well-known/openid-credential-issuer` on the root; `tls-proxy` maps the root well-known
  routes to Certify's `/v1/certify/.well-known/...` as upstream's `certify-nginx.conf` does. The Certify listener
  asks for a client certificate without checking it (`ssl_verify_client optional_no_ca`), for the suite's mTLS
  variants. Details: [`certify/README.md`](certify/README.md).
- MinIO is reached as `http://minio:9000` with path-style requests, which the testrigs' stock `S3Adapter` uses.
  Details: [`minio/README.md`](minio/README.md).
- `tls-proxy` resolves its backends per request through Docker's DNS, so it starts with any profile and answers
  502 for a backend that the active profiles leave out.
- Host ports stay in 18000-18999 and bind to 127.0.0.1 only; nothing listens on 8080, 8443 or 4501 on the host.

## Run-time keys (`pki-init`)

`pki-init` runs [`pki/generate.py`](pki/generate.py) (Python standard library and the `openssl` command) and writes
test-only key material to `$HARNESS_RUN_DIR/pki`. Nothing here is ever committed.

| File | Use |
|---|---|
| `ca.crt`, `ca.key` | Test CA (EC P-256, 825 days). Clients in the network trust it with `--cacert /pki/ca.crt`. |
| `tls/verify.inji.test.crt`, `.key`; `tls/certify.inji.test.crt`, `.key` | TLS server certificates for `tls-proxy` (leaf followed by the CA, 397 days). |
| `suite-mtls-client.crt`, `.key` | Client certificate for the suite's mTLS client-authentication and sender-constraint variants. |
| `suite-signing.crt`, `.key`, `suite-signing.jwk.json` | The suite's credential signing key (ES256) as a private JWK with `x5c`, for `credential.signing_jwk` in verifier test plans. Inji Verify reads the issuer key from the first `x5c` certificate. `kid` is the RFC 7638 thumbprint. |
| `manifest.json` | Settings, creation time, CA expiry and SHA-256 fingerprints; written last. |

- A later run reuses the set when `manifest.json` matches the settings, every file exists and the CA is valid for at
  least 30 more days. Keys therefore stay the same between runs, which keeps results comparable.
- New set: `PKI_FORCE=1 bash scripts/dc.sh --profile verify up -d --wait`, or delete `$HARNESS_RUN_DIR/pki`.
- Private keys are written with mode 0600, certificates with 0644.

## Smoke test (`smoke.sh`)

`bash compose/smoke.sh PROFILE...` (profiles `suite`, `verify`, `certify`, `reports`) refuses to start when containers of the project
already exist, checks that the published ports are free, runs `up --wait`, runs the checks, samples `docker stats`
every 3 seconds, and always ends with `down --volumes`. It exits 0 only when every check passed.

| Check | What it proves |
|---|---|
| `start` | Every service of the profiles became healthy (limit `SMOKE_START_TIMEOUT`, default 420 s); prints the time. |
| `pki` | The four certificates verify against the test CA; the signing JWK has `x5c`. |
| `suite` | `GET /api/server` answers through nginx from inside the network (`probe`) and from the host, and the version matches the image tag. |
| `suite-mtls` | The mTLS listener on 18444 answers. |
| `verify` | Over TLS with the test CA: `POST /v1/verify/v2/vp-request` with client id `x509_san_dns:verify.inji.test` and a DCQL query for `dc+sd-jwt` returns 201 with a `requestUri` under `https://verify.inji.test:18451/v1/verify`; that URI returns a request object (`application/oauth-authz-req+jwt`) whose header has `x5c` and whose claims carry the client id and a `response_uri` under the same base URL. |
| `certify` | Over TLS: `GET /.well-known/openid-credential-issuer` at the root returns `credential_issuer` `https://certify.inji.test:18450`, the credential endpoint under `/v1/certify`, and Certify itself as first authorization server. Prints the image's `commit_id` label. |
| `certify-as` | `GET /.well-known/oauth-authorization-server` names the same issuer, `token_endpoint` `https://certify.inji.test:18450/v1/certify/oauth/token` and the pre-authorized code grant. |
| `certify-preauth` | `POST /v1/certify/pre-authorized-data` for the seeded `FarmerCredential` returns an `openid-credential-offer://` link; the offer it points to has the issuer and a pre-authorized code. |
| `certify-token` | That code, redeemed at the token endpoint, gives a `Bearer` access token whose `iss` is the issuer (Certify validates its own tokens). |
| `minio` | `minio-mc stat local/automationtests` finds the bucket; an object is written, read and deleted with signed path-style requests (`curl --aws-sigv4` to `http://minio:9000/automationtests/...`); the S3 port answers on the host. |
| `stats` | Peak memory per service and in total. |
| `teardown` | No container or volume of the project is left. |

Measurements, logs (`up.log`, `down.log`, `probe.log`, and `compose.log` after a failure) and `smoke.json` go to
`$HARNESS_RUN_DIR/smoke/<UTC time>-<profiles>/`.

Output on 2026-10-04 (Windows 11, Docker Desktop 29.7.2 with an 8 GB VM shared with other projects, images
already pulled):

```text
ports PASS 18443 18444 18451 18461 free
start PASS 65s to healthy (verify)
pki PASS 4 certificates chain to the test CA, signing JWK has x5c
  network: {"build_time":"2026-09-18T14:29:43Z","tag":"release-v5.3.1","version":"5.3.1","external_ip":null,"revision":"440eec8"}
suite PASS 5.3.1
suite-mtls PASS 18444
  POST /v2/vp-request -> 201, transactionId txn_fd5c68e2-8e4a-4373-b1c0-a0652e05352c
  GET request_uri -> 200 application/oauth-authz-req+jwt;charset=UTF-8, header alg EdDSA
verify PASS 201 x509_san_dns request_uri
  peak memory (MiB): suite-server 431 verify-service 277 suite-mongodb 119 verify-db 58 suite-nginx 22 tls-proxy 8
stats PASS peak 915 MiB total, start 65s
teardown PASS
```

Measured on the same day, four runs: start to healthy 34-76 s for `verify` (the spread follows the load other
projects put on the shared Docker VM) and 66 s for `suite`; peak memory 880-925 MiB in total for `verify` and
576 MiB for `suite`.

`bash compose/smoke.sh certify reports` on 2026-10-04, same machine and conditions (other projects' stacks were
running on the same Docker VM):

```text
ports PASS 18443 18444 18450 18451 18460 18900 18901 free
start PASS 134s to healthy (certify reports)
pki PASS 4 certificates chain to the test CA, signing JWK has x5c
  network: {"build_time":"2026-09-18T14:29:43Z","tag":"release-v5.3.1","version":"5.3.1","external_ip":null,"revision":"440eec8"}
suite PASS 5.3.1
suite-mtls PASS 18444
  image commit_id label: d6635da
  credential_endpoint https://certify.inji.test:18450/v1/certify/issuance/credential
certify PASS credential_issuer=https://certify.inji.test:18450
  token_endpoint https://certify.inji.test:18450/v1/certify/oauth/token
certify-as PASS token_endpoint
  offer https://certify.inji.test:18450/v1/certify/credential-offer-data/4f876282-98e6-48dc-afe0-288fc901fded
certify-preauth PASS offer
  POST /oauth/token -> 200, token_type Bearer, iss https://certify.inji.test:18450
certify-token PASS Bearer
  path-style PUT, GET and DELETE of automationtests/smoke/20261004T103927Z-303207.txt
minio PASS bucket automationtests
  peak memory (MiB): certify 615 suite-server 541 suite-mongodb 163 minio 85 certify-db 54 suite-nginx 32 tls-proxy 9
stats PASS peak 1499 MiB total, start 134s
teardown PASS
```

One run so far; Certify alone needs most of the 134 s (Spring Boot start and the keymanager's first key
generation).

## Upstream files

Imported unchanged in their own commits first, then changed in separate commits, so `git log -p -- <file>` shows
the team's diff.

| File | Upstream | Licence | Team change |
|---|---|---|---|
| `suite/nginx.conf` | `openid/conformance-suite` `nginx/nginx.conf` at tag `release-v5.3.1` (commit `440eec8`) | MIT, [`suite/LICENSE.txt`](suite/LICENSE.txt) | `listen 18443`/`18444` and the matching `X-Forwarded-Port` headers instead of 8443/8444; `proxy_pass` to `suite-server`; header comment |
| `verify/init.sql` | `inji/inji-verify` `docker-compose/db-init/init.sql` at `release-1.0.x` commit `6a6ab3b` | Apache-2.0, [`verify/LICENSE`](verify/LICENSE) | `vp_submission` brought in line with the upstream `db_scripts` DDL of the same commit (response code columns, nullable token, keys): without them the 1.0.x service answers HTTP 500 to every wallet response |
| `certify/config/certify-default.properties` | `inji/inji-certify` `docker-compose/docker-compose-injistack/config/` at `release-1.0.x` commit `203b143` | Apache-2.0, [`certify/LICENSE`](certify/LICENSE) | Certify as its own authorization server, HTTPS domain, database host, passwords from `env.local`; see [`certify/README.md`](certify/README.md) |
| `certify/config/certify-csvdp-farmer.properties`, `certify/certify_init.sql`, `certify/certify-nginx.conf` | same commit, `docker-compose/docker-compose-injistack/` | Apache-2.0 | none (`certify-nginx.conf` is the reference for `tls-proxy/sites/certify.conf`, not mounted) |

`docker-compose.yml` follows the suite's `docker-compose-prebuilt.yml` and Inji Verify's
`docker-compose/docker-compose.yml` (release-1.0.x) for service settings, with these differences: harness ports
and names, generated database password, no `user: root` for Verify (the image's own user works), the QA image
`injistackqa/inji-verify-service:1.0.x` because the `1.0.0-alpha.2` tag in the upstream file is not published and
`1.0.0-alpha.1` cannot sign `x509_san_dns` requests, and no Verify UI (the harness drives Verify's API). For Inji
Certify it follows `docker-compose/docker-compose-injistack/docker-compose.yaml` of inji-certify (release-1.0.x):
same `user: root`, Spring settings and mount paths; harness ports and names; the profile `preauth` added; no
`certify-nginx` (replaced by the `tls-proxy` site), no Mimoto and no Inji Web (wallet side, which the suite plays);
the keystore in a named volume instead of a folder of the checkout.

## Tests

| Command | Covers |
|---|---|
| `bash scripts/tests/test-pki.sh` | `pki/test_generate.py`: chain, key usages, JWK members and lengths, `x5c` matches the key, thumbprint, reuse and regeneration rules, private-scalar padding |
| `bash scripts/tests/test-dc.sh` | `dc.sh` with a stub `docker`: env file creation and append-only updates, compose arguments, native paths, project-name guard |
| `bash scripts/tests/test-smoke.sh` | `smoke.sh` argument handling, memory-peak parsing, JSON, JWT and URL helpers, reading `env.local` |
| `bash compose/smoke.sh verify`, `bash compose/smoke.sh certify reports` | The whole stack, as above (needs Docker) |

`bash scripts/check.sh shell` runs shellcheck on every script and then all three test scripts.

## Troubleshooting

[docs/troubleshooting.md](../docs/troubleshooting.md#setup-and-the-stack).
