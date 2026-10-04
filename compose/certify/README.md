# compose/certify

Configuration of Inji Certify (services `certify` and `certify-db` in the root
[`docker-compose.yml`](../../docker-compose.yml), profile `certify`). Certify is the credential issuer under test; the
OpenID Foundation conformance suite plays the wallet against it.

## What runs

| Item | Value |
|---|---|
| Image | `injistackqa/inji-certify-with-plugins:develop`, pinned by digest, label `commit_id` `d6635da` (built 2026-09-09). Override with `CERTIFY_IMAGE`. |
| Why this image | The newest 1.0-line build with DPoP support. The `1.0.0-alpha.1` release image has no DPoP code. `compose/smoke.sh certify` prints the `commit_id` label of the image it ran. |
| Database | `postgres:15` with the upstream [`certify_init.sql`](certify_init.sql) (schema and the seeded `FarmerCredential` configuration). Named volume `certify-db-data`. |
| Keystore | PKCS12 file created by Certify at first start in the named volume `certify-keystore`. It holds the master keys; the database holds keys wrapped by them, so `down -v` removes both together. |
| Issuer identifier | `https://certify.inji.test:18450` (the `tls-proxy` service, see [`../tls-proxy/sites/certify.conf`](../tls-proxy/sites/certify.conf)). |
| Debug access | `http://127.0.0.1:18460/v1/certify/...` on the host, plain HTTP, never used by the conformance runs. |
| Memory | limit 1 GiB, Java heap 50 % of it. |

Spring profiles, in order (a later one overrides an earlier one): `default` (`certify-default.properties`),
`csvdp-farmer` (`certify-csvdp-farmer.properties`, unchanged upstream file), `preauth`
([`config/certify-preauth.properties`](config/certify-preauth.properties), team file).

## Changes to the upstream configuration

The four upstream files and the `LICENSE` came in unchanged in commit "import: upstream inji/inji-certify@203b143
(Apache-2.0)" from `docker-compose/docker-compose-injistack/` of the `release-1.0.x` branch. Every later change is a
separate commit and is marked with a `# harness:` comment in the file, so `git log -p -- compose/certify` shows the
whole team diff.

| File | Change | Reason |
|---|---|---|
| `config/certify-default.properties` | `mosip.certify.domain.url=https://certify.inji.test:18450` | The suite requires https for the issuer and all endpoints. No path, so the issuer metadata is at `<origin>/.well-known/openid-credential-issuer` as OpenID4VCI 1.0 prescribes. |
| same | `mosip.certify.authorization.url`, `authn.issuer-uri`, `authn.jwk-set-uri`, `authn.allowed-audiences` point at Certify itself | "Use certify as Auth Server" in upstream `docs/technical_docs/Local_Development.md`. Upstream points at the public eSignet mock, which the harness must not depend on. The key set is read from `http://localhost:8090` inside the container, so the JVM need not trust the run-time test CA. |
| same | `spring.datasource.password=${CERTIFY_DB_PASSWORD}`, `mosip.kernel.keymanager.hsm.keystore-pass=${CERTIFY_KEYSTORE_PASSWORD}` | Passwords are generated per installation into `$HARNESS_RUN_DIR/env.local` by `scripts/dc.sh`; Spring reads the environment variables Compose passes in. |
| same | `mosip.certify.database.hostname=certify-db` | Compose service name. |
| `config/certify-preauth.properties` (new) | `mosip.certify.integration.data-provider-plugin=PreAuthDataProviderPlugin`; issuer DID `did:web:certify.inji.test%3A18450` | Credential data come from the pre-authorized offer (upstream `docs/technical_docs/Pre_Authorized_Code.md`), so no identity system and no browser login are needed. The upstream farmer profile points the DID at a personal tunnel URL. |
| `certify-nginx.conf` | none, not mounted | Kept as the source of the root well-known routes that [`../tls-proxy/sites/certify.conf`](../tls-proxy/sites/certify.conf) reproduces with TLS. |
| `certify_init.sql`, `config/certify-csvdp-farmer.properties`, `LICENSE` | none | |

Known upstream quirk, left as is: `certify-default.properties` sets `mosip.certify.pre-auth-code.*-expiry-seconds`,
but the code reads `mosip.certify.pre-auth.*`, so those three values have no effect and the code defaults apply.

## Endpoints the harness uses

All through `https://certify.inji.test:18450` (inside the compose network only; trust `/pki/ca.crt`).

| Endpoint | Used by |
|---|---|
| `GET /.well-known/openid-credential-issuer` | suite (issuer metadata), smoke check `certify` |
| `GET /.well-known/oauth-authorization-server` | suite (Certify as its own authorization server), smoke check `certify-as` |
| `POST /v1/certify/pre-authorized-data` | runner (issuer back office: creates an offer with the claims), smoke check `certify-preauth` |
| `GET /v1/certify/credential-offer-data/{id}` | suite (fetches the offer by reference) |
| `POST /v1/certify/oauth/token` | suite (redeems the pre-authorized code), smoke check `certify-token` |
| `POST /v1/certify/nonce`, `POST /v1/certify/issuance/credential` | suite |
| `POST /v1/certify/credential-configurations` | runner (adds the `dc+sd-jwt` configuration the issuer plan requests) |

The back-office APIs need no authentication in this configuration (upstream's `ignore-auth-urls`); the harness only
exposes them inside the compose network and on 127.0.0.1.

## Try it

```bash
bash scripts/dc.sh --profile certify up -d --wait
bash scripts/dc.sh run --rm probe -sS --cacert /pki/ca.crt https://certify.inji.test:18450/.well-known/openid-credential-issuer
bash scripts/dc.sh --profile certify down -v
```

`bash compose/smoke.sh certify` does the same and also creates and redeems an offer; see
[`../README.md`](../README.md#smoke-test-smokesh).
