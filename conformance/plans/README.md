# Plan templates

One JSON file per suite test plan the harness runs, named `<component>.<plan>.json`. `inji-conformance run
--component <component>` picks the template whose `component` and `track` match. A template says which suite plan
runs with which variant (the options that select the protocol flavour), the suite configuration, and what the
handoff responder needs to play the person who normally clicks through the test.

| File | Plan | Variant | Status |
|---|---|---|---|
| `verify.oid4vp-1final-verifier.json` | `oid4vp-1final-verifier-test-plan` (OpenID4VP 1.0 Final, suite plays the wallet) | `plain_vp`, `sd_jwt_vc`, `x509_san_dns`, `request_uri_signed`, `direct_post` | In use since 2026-10-04 |

## Format

| Key | Meaning |
|---|---|
| `component` | `verify` or `certify` |
| `track` | `gate` (the 1.0 Final plans the benchmark gates on, default) or `haip` (readiness track) |
| `plan` | Suite test plan name, as `GET /api/plan/available` lists it |
| `variant` | Variant name to value. Values may use letters, digits and `_-=,./` (the grammar of the suite's `run-test-plan.py`) |
| `modules` | Modules to run; empty means every module of the plan. `--modules` on the command line overrides it |
| `parameters` | Default values for `${name}` variables, for example the client id host |
| `certs_keys` | File name in the staged `certs-keys/` folder to file name in the run's key folder (`$HARNESS_RUN_DIR/pki`, written by the `pki-init` container) |
| `config` | The suite configuration (see below) |
| `handoff` | Settings of the handoff responder; `authorization_request` for Inji Verify: `client_id`, `response_mode`, `dcql_query` |
| `review` | Verdict Inji Verify must show for a module the suite ends in REVIEW: `default` and the list of `invalid` modules |

Inside `config` and `handoff`:

- `${run_id}`, `${target_url}` (Inji's base URL), `${suite_url}` and every key of `parameters` are replaced. An
  unknown name stops the run before anything reaches the suite.
- `{"$certs_keys": "suite-signing.jwk.json"}` is written as the suite's own placeholder `{suite-signing.jwk.json}`
  without quotes. `run-test-plan.py` replaces it with the file's content from `certs-keys/` when it creates the plan,
  so the rendered configuration in the run folder never holds a private key.
- `$comment` keys are notes and are dropped.
- The `alias` must contain `${run_id}`. The handoff responder only touches tests with this run's alias, so two runs
  can share one suite.

## The verifier template, field by field

- `client.client_id` `test.example.com`: for `x509_san_dns` the suite adds the `x509_san_dns:` prefix and checks the
  request's `client_id` against it. The host is the DNS name in the certificate Inji Verify signs its request objects
  with (the test keystore bundled in the `1.0.x` image).
- `credential.signing_jwk`: the run's private key with an `x5c` chain, made by `pki-init`. The suite signs the SD-JWT
  credential it presents with it; Inji Verify reads the issuer key from `x5c`.
- `browser`: temporary. Positive tests end with a screenshot placeholder for the verifier's result screen. This
  block lets the suite's built-in browser fill it from the suite's own evidence page, as the suite's
  `vp-verifier-test-config.json` does. A later version uploads an image of Inji Verify's own verdict instead.
- `handoff.authorization_request`: the body of `POST /v1/verify/v2/vp-request`. The DCQL query asks for one
  `dc+sd-jwt` credential with `vct` `urn:eudi:pid:1`, the type the suite issues.

## Rendered output

`inji-conformance run` writes the rendered configuration to `<out>/<component>/config/<template name>.json`. It is the
same format as the suite's own sample configurations, so it can also be uploaded to the hosted suite at
<https://www.certification.openid.net> by hand once the `{...}` placeholder is replaced with a key.
