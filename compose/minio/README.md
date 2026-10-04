# compose/minio

Local S3 store for the api-testrig reports (service `minio` in the root
[`docker-compose.yml`](../../docker-compose.yml), profile `reports`; client `minio-mc`, profile `tools`).

The problem statement asks for conformance results in the same minio/S3 `automationtests` bucket the Inji api-testrigs
already upload their Extent reports to. The testrigs' stock `S3Adapter` (API Test Commons 1.5.0 and 1.6.0) builds its
client with `enablePathStyleAccess()`, so it addresses `http://minio:9000/automationtests/<key>`; no bucket host
names (`MINIO_DOMAIN`) are needed.

| Item | Value |
|---|---|
| Server image | `pgsty/minio:RELEASE.2026-08-04T00-00-00Z`, pinned by digest. Override with `MINIO_IMAGE`. |
| Client image | `pgsty/mc:RELEASE.2026-09-16T00-00-00Z`, pinned by digest. Override with `MINIO_MC_IMAGE`. |
| Why these images | MinIO Inc. no longer publishes `minio/minio` or `minio/mc` images (Docker Hub and quay.io refuse the pull, checked 2026-10-04). The pgsty images are community builds of the same AGPL-3.0 source. MinIO runs unmodified as a separate program; the harness only talks S3 to it. |
| Credentials | `MINIO_ROOT_USER` (default `harness`) and `MINIO_ROOT_PASSWORD` (generated into `$HARNESS_RUN_DIR/env.local` by `scripts/dc.sh`). |
| Bucket | `automationtests` (`MINIO_BUCKET` overrides it), created by [`init.sh`](init.sh). |
| Data | named volume `minio-data`, removed by `down -v`. |
| Ports | S3 API `http://127.0.0.1:18900`, web console `http://127.0.0.1:18901` (log in with the root user and password from `env.local`). Inside the network: `http://minio:9000`. |
| Memory | limit 512 MiB. |

## Bucket creation (minio-init)

[`init.sh`](init.sh) waits until the server answers (`mc ready`), then runs `mc mb --ignore-existing`. It runs as the
`post_start` hook of the `minio` container, with the image's own `mc` and the alias `local` that `MC_HOST_local`
defines. The healthcheck is `mc stat local/automationtests`, so `up --wait` returns only once the bucket exists.

It is a hook and not a separate one-shot `minio-init` container because `docker compose up --wait` fails when a
one-shot container exits and no other service depends on it (measured on 2026-10-04 with Compose 5.5.1: "container
... exited (0)", exit status 1), and nothing in the `reports` profile waits for one.

## Use

```bash
bash scripts/dc.sh --profile reports up -d --wait
bash scripts/dc.sh run --rm minio-mc ls --recursive local/automationtests
bash scripts/dc.sh --profile reports down -v
```

Testrig settings (environment of the testrig container, wired by the testrig lane): endpoint `http://minio:9000`,
access key `$MINIO_ROOT_USER`, secret key `$MINIO_ROOT_PASSWORD`, bucket `automationtests`.

`bash compose/smoke.sh reports` checks the bucket with `minio-mc`, then writes, reads and deletes an object with
signed path-style requests from the `probe` container (`curl --aws-sigv4`), the same addressing `S3Adapter` uses.
