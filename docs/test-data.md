# Test data

Everything the runs use as input, and every secret, with where it is made and kept. No key or password is
committed; `bash scripts/check.sh secrets` scans the repository for them.

## Inji Certify

| Data | Value | Where |
|---|---|---|
| Credential configuration | id `InjiConformanceSdJwtVc`, format `dc+sd-jwt`, `vct` `urn:inji-conformance:vct:farmer:1` (a URN, so the suite does not fetch type metadata), ES256 with Certify's key `CERTIFY_VC_SIGN_EC_R1` / `EC_SECP256R1_SIGN`, selectively disclosable `fullName`, claims `fullName`, `dateOfBirth`, `gender`, scope `inji_conformance_sd_jwt_vc` | `conformance/plans/certify.oid4vci-1_0-issuer.json`, block `seed`; created by `inji-conformance seed certify` |
| Offer claims | `{"fullName": "Asha Test-Farmer", "dateOfBirth": "1990-01-15", "gender": "Female"}` (made-up person) | the same file, block `handoff.credential_offer` |
| Transaction code | 6 random digits per offer, offer valid 600 s | made by the responder per offer |
| Upstream seed data | the `FarmerCredential` (`ldp_vc`) configuration and the CSV data provider of upstream's compose set-up | `compose/certify/` (upstream files, see its README) |

## Inji Verify

| Data | Value | Where |
|---|---|---|
| Client id (default) | `redirect_uri:https://verify.inji.test:18451/v1/verify/v2/vp-submission/direct-post` | `conformance/plans/verify.oid4vp-1final-verifier.json` |
| Client id (alternative) | `x509_san_dns:verify.inji.test` | `...-x509-san-dns.json` |
| DCQL query | one credential `pid`, format `dc+sd-jwt`, `vct_values` `["urn:eudi:pid:1"]` | both templates, block `handoff.authorization_request` |
| Presented credential | an SD-JWT VC the suite makes and signs with the run's `suite-signing` key (`x5c` from the test CA); tampered in the negative modules | the suite, from the template's `credential.signing_jwk` |
| Expected verdicts | `valid` by default; `invalid` for the tampered modules listed in `review.invalid` | the template's `review` block |

## Generated at run time

| Material | Made by | Kept in | Lifetime |
|---|---|---|---|
| `VERIFY_DB_PASSWORD`, `CERTIFY_DB_PASSWORD`, `CERTIFY_KEYSTORE_PASSWORD`, `MINIO_ROOT_PASSWORD`, `VERIFY_KEYSTORE_PASSWORD` (32 hex characters each) | `scripts/dc.sh` | `$HARNESS_RUN_DIR/env.local` (mode 600) | until deleted together with the volumes |
| Test CA (EC P-256) | `pki-init` (`compose/pki/generate.py`) | `$HARNESS_RUN_DIR/pki/ca.crt`, `ca.key` | 825 days; regenerated 30 days before expiry or with `PKI_FORCE=1` |
| TLS certificates for `certify.inji.test`, `verify.inji.test` | `pki-init` | `pki/tls/` | 397 days |
| Suite mTLS client certificate | `pki-init` | `pki/suite-mtls-client.*` | 397 days |
| Suite credential signing key (ES256 JWK with `x5c`) | `pki-init` | `pki/suite-signing.*` | 397 days |
| Inji Verify request signing keystore (Ed25519, certificate for `verify.inji.test`, leaf only) | `pki-init` | `pki/verify-request-signing.p12`, protected by `VERIFY_KEYSTORE_PASSWORD` | 397 days |
| Wallet client key sets `client`, `client2` (P-256 private JWK sets) | the runner (`keys.py`) | `<run>/<component>/suite-scripts/certs-keys/`, deleted after the plan | one run |
| Inji Certify's signing keys | Inji Certify | its keystore volume and database | until `down -v` |

The suite's exports (`<run>/<component>/exports/*.zip`) contain the suite configuration with the run's private keys
filled in: they stay in the run folder and are never committed; the CI artifacts remove them.

## Suite configuration fields

| Template | Fields set |
|---|---|
| issuer | `alias` (`inji-certify-<run id>`), `description`, `vci.credential_issuer_url`, `vci.credential_configuration_id`, `client.client_id` and `client.jwks`, `client2.*`, `mtls.cert` / `mtls.key`, `mtls2.*` |
| verifier | `alias` (`inji-verify-<run id>`), `description`, `credential.signing_jwk`, and for x509_san_dns `client.client_id` (`verify.inji.test`) |
| HAIP verifier | as x509_san_dns, plus `client.request_object_trust_anchor_pem` (the test CA) |
