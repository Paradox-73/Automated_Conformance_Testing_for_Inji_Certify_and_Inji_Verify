# compose

Assets for the root `docker-compose.yml`: one Docker Compose project (`ps01-harness`) that runs the OpenID
Foundation conformance suite, Inji Certify, Inji Verify and MinIO side by side.

Lane: platform. Status on 2026-10-04: empty; the folders below are the plan.

## Planned contents

| Path | Purpose |
|---|---|
| `suite/` | Conformance suite: server, MongoDB and the suite's nginx front end, with the nginx configuration adjusted to the harness ports |
| `certify/` | Inji Certify and its PostgreSQL database; `certify/config/certify-default.properties` comes from the inji-certify repository, imported unchanged first |
| `verify/` | Inji Verify service and its PostgreSQL database |
| `tls-proxy/` | One nginx that gives Inji Certify and Inji Verify HTTPS host names on the compose network |
| `pki/` | One-shot container that creates the test CA, TLS certificates and signing keys at run time |
| `minio/` | Local S3 with the `automationtests` bucket for testrig reports |
| `smoke.sh` | Starts one profile and checks that every service answers |

## Rules

- Host ports are in 18000-18999 and bound to 127.0.0.1. Ports 8080, 8443 and 4501 are never used on the host.
- Keys, certificates and passwords are generated at run time into `$HARNESS_RUN_DIR`, never committed.
- Image versions are pinned as overridable defaults in `docker-compose.yml`.
- Upstream configuration files are imported unchanged in their own commit before any change.
  `certify/config/certify-default.properties` holds the upstream development passwords and is listed in
  `.gitguardian.yaml`.
