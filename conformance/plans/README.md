# Plan templates

One JSON file per suite test plan the harness runs, named `<component>.<plan>.json`. `inji-conformance run
--component <component>` picks the template whose `component` and `track` match. A template says which suite plan
runs with which variant (the options that select the protocol flavour), the suite configuration, and what the
handoff responder needs to play the person who normally clicks through the test.

| File | Plan | Variant | Status |
|---|---|---|---|
| `verify.oid4vp-1final-verifier.json` | `oid4vp-1final-verifier-test-plan` (OpenID4VP 1.0 Final, suite plays the wallet) | `plain_vp`, `sd_jwt_vc`, `redirect_uri`, `url_query`, `direct_post` | Default since 2026-10-14: 11 of 11 modules conform |
| `verify.oid4vp-1final-verifier-x509-san-dns.json` | the same plan | `plain_vp`, `sd_jwt_vc`, `x509_san_dns`, `request_uri_signed`, `direct_post` | Alternative (`--template`); in use 2026-10-04 to 2026-10-14; stops at the request object signature ([finding](../../docs/findings/verify-request-signing-eddsa-only.md)) |
| `certify.oid4vci-1_0-issuer.json` | `oid4vci-1_0-issuer-test-plan` (OpenID4VCI 1.0 Final, suite plays the wallet) | `vci`, `sd_jwt_vc`, `pre_authorization_code`, `issuer_initiated`, `private_key_jwt`, `dpop`, `simple`, `unsigned`, `plain` | First live run 2026-10-14: all 15 modules complete |
| `certify.oid4vci-1_0-issuer-haip.json`, `verify.oid4vp-1final-verifier-haip.json` | the HAIP plans | see the files | Readiness track (`--track haip`), never gating; first run 2026-10-14 |

A template with `"alternative": true` runs only when named with `--template`; each component and track has exactly
one default.

## Format

| Key | Meaning |
|---|---|
| `component` | `verify` or `certify` |
| `track` | `gate` (the 1.0 Final plans the benchmark gates on, default) or `haip` (readiness track) |
| `plan` | Suite test plan name, as `GET /api/plan/available` lists it |
| `variant` | Variant name to value. Values may use letters, digits and `_-=,./` (the grammar of the suite's `run-test-plan.py`) |
| `modules` | Modules to run; empty means every module of the plan. `--modules` on the command line overrides it |
| `parameters` | Default values for `${name}` variables, for example the client id host |
| `certs_keys` | File name in the staged `certs-keys/` folder to how the file is made (see below) |
| `config` | The suite configuration (see below) |
| `seed` | What the component needs before the plan can run. Inji Certify: `credential_configuration`, the body of `POST /v1/certify/credential-configurations` |
| `handoff` | Settings of the handoff responder. Inji Verify: `authorization_request` with `client_id`, `response_mode`, `dcql_query`. Inji Certify: `credential_offer` with `credential_configuration_id`, `claims`, `tx_code_length` (4 to 8, or 0 for no code), `expires_in` (60 to 86400 seconds) |
| `review` | Verdict Inji Verify must show for a module the suite ends in REVIEW: `default` and the list of `invalid` modules |

A `certs_keys` entry is one of:

- `"<file>"`: copy that file of the run's key folder (`$HARNESS_RUN_DIR/pki`, written by the `pki-init` container);
- `{"from": "<file>", "as": "json_string"}`: write that file's text as one JSON string literal. For PEM
  certificates and keys inside the configuration: `run-test-plan.py` turns the newlines of a `certs-keys` file into
  spaces, and a JSON string literal keeps them as `\n`;
- `{"generate": "p256_jwks"}`: write a fresh P-256 private JWK set, made for this run only.

Inside `config`, `handoff` and `seed`:

- `${run_id}`, `${target_url}` (Inji's base URL), `${suite_url}` and every key of `parameters` are replaced. An
  unknown name stops the run before anything reaches the suite.
- `{"$certs_keys": "suite-signing.jwk.json"}` is written as the suite's own placeholder `{suite-signing.jwk.json}`
  without quotes. `run-test-plan.py` replaces it with the file's content from `certs-keys/` when it creates the plan,
  so the rendered configuration in the run folder never holds a private key.
- `$comment` keys are notes and are dropped.
- `vcTemplate` inside a `seed` entry is sent as written: it is Inji Certify's own template, and its `${claim}`
  placeholders are filled by Inji Certify at issuance. `seed` gets `${target_url}` and the `parameters`, never
  `${run_id}`, so that seeding gives the same result on every run.
- The `alias` must contain `${run_id}`. The handoff responder only touches tests with this run's alias, so two runs
  can share one suite.

## The verifier template, field by field

- `client.client_id` `test.example.com`: for `x509_san_dns` the suite adds the `x509_san_dns:` prefix and checks the
  request's `client_id` against it. The host is the DNS name in the certificate Inji Verify signs its request objects
  with (the test keystore bundled in the `1.0.x` image).
- `credential.signing_jwk`: the run's private key with an `x5c` chain, made by `pki-init`. The suite signs the SD-JWT
  credential it presents with it; Inji Verify reads the issuer key from `x5c`.
- No `browser` block (removed 2026-10-14): positive and tampered tests end with a screenshot placeholder for the
  verifier's result screen, and the runner uploads an image of Inji Verify's own verdict into it
  ([docs/handoffs.md](../../docs/handoffs.md)).
- `handoff.authorization_request`: the body of `POST /v1/verify/v2/vp-request`. The DCQL query asks for one
  `dc+sd-jwt` credential with `vct` `urn:eudi:pid:1`, the type the suite issues.

## The issuer template, field by field

- `variant`: the pre-authorized code flow, started by the issuer's offer (`vci_grant_type`
  `pre_authorization_code`, `vci_authorization_code_flow_variant` `issuer_initiated`), so no login page is needed;
  an SD-JWT VC (`credential_format` `sd_jwt_vc`); `sender_constrain` `dpop`. `run --variant sender_constrain=mtls`
  runs the mTLS flavour. Measured 2026-10-14: both reach the same conditions and neither reaches credential
  issuance (the requests fail before any sender-constraint check), so the gate keeps `dpop`
  ([conformance/README.md](../README.md)).
- `parameters.credential_configuration_id` `InjiConformanceSdJwtVc`: used by `config.vci`, the `seed` block and
  the `handoff` block, so all three name the same configuration.
- `config.vci.credential_issuer_url`: Inji Certify's issuer identifier, an origin without a path, so the suite
  finds the metadata at `<origin>/.well-known/openid-credential-issuer`.
- `config.client`, `config.client2`: the suite's two wallet clients (the second for the multiple-clients module),
  each with a JWK set generated for the run.
- `config.mtls`, `config.mtls2`: the client certificate and key from `pki-init`, used when
  `sender_constrain=mtls`.
- `seed.credential_configuration`: a `dc+sd-jwt` configuration with a URN `vct` (so the suite does not fetch
  SD-JWT VC type metadata), signed with ES256, with the claims `fullName`, `dateOfBirth` and `gender`. `vcTemplate`
  is written as a JSON object here; the runner sends it base64-encoded, as Inji Certify requires.
- `handoff.credential_offer`: the body of `POST /v1/certify/pre-authorized-data` for every offer. Its claims must
  be exactly the configuration's claims. Each offer gets a new random numeric transaction code of
  `tx_code_length` digits.

## Rendered output

`inji-conformance run` writes the rendered configuration to `<out>/<component>/config/<template name>.json`. It is the
same format as the suite's own sample configurations, so it can also be uploaded to the hosted suite at
<https://www.certification.openid.net> by hand once every `{...}` placeholder is replaced with a key.
