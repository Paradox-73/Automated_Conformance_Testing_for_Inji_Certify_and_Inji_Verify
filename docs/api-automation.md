# API automation

Every HTTP call the harness makes, and how it reuses the conformance suite's own automation script. Source:
`runner/src/inji_conformance/` (`suite.py`, `inji_certify.py`, `inji_verify.py`, `handoff.py`, `run.py`).

## How `run-test-plan.py` is reused

`third_party/oidf-conformance-suite/scripts/` holds the suite's `run-test-plan.py`, `conformance.py` and
`test_plan_parser.py` from release-v5.3.1, unchanged (MIT; `bash third_party/reimport.sh check` proves it). For each
component the runner:

1. renders the plan template (`conformance/plans/<component>.<name>.json`) into `config/<name>.json` with
   placeholders such as `{suite-signing.jwk.json}` instead of keys;
2. copies the three scripts into the run folder with a `certs-keys/` folder holding this run's keys (the script
   fills the placeholders from it, so no key is in the rendered file);
3. writes the benchmark entries for this configuration into `benchmark/` and starts

   ```text
   python run-test-plan.py --export-dir exports \
     --expected-failures-file benchmark/<c>.expected-failures.json \
     --expected-skips-file benchmark/<c>.expected-skips.json \
     <plan>[<variant>=<value>]...[:<modules>] config/<name>.json
   ```

   with `CONFORMANCE_SERVER`, `CONFORMANCE_DEV_MODE=1` and `CONFORMANCE_MAX_CONSECUTIVE_FAILURES=1000`;
4. runs the handoff responder next to it ([handoffs.md](handoffs.md));
5. after the script, downloads the HTML export, reads every module from the suite, applies the benchmark, and
   compares its gate with the script's exit code (the same benchmark files): a disagreement ends the run with
   exit 2;
6. deletes `certs-keys/`.

## Conformance suite API (`suite.py`)

The suite runs with its `dev` profile, so no API token is needed; its certificate is self-signed.

| Call | Used for |
|---|---|
| `GET /api/server` | readiness and suite version |
| `GET /api/runner/running` | the tests the responder watches |
| `GET /api/runner/{id}` | exposed endpoints (`authorization_endpoint`, `credential_offer_endpoint`, `tx_code_endpoint`) and browser state (`uploadsRequired`) of a waiting test |
| `POST /api/runner/{id}` | start a test left in CONFIGURED |
| `POST /api/runner/browser/{id}/visit?url=` | mark a front-channel URL visited |
| `GET /api/info/{id}`, `GET /api/log/{id}` | status, result and log entries of each module |
| `GET /api/log/{id}/images`, `POST /api/log/{id}/images/{placeholder}` | find and fill the screenshot placeholder (body `data:image/png;base64,...`, `text/plain`) |
| `GET /api/plan/{id}` | modules of the plan and their test ids |
| `GET /api/plan/exporthtml/{id}` | the HTML export, extracted to `exports/html/` |

Example, the placeholder upload the responder makes:

```text
POST https://localhost.emobix.co.uk:18443/api/log/0nM1d1G0eTaBQ1F/images/WblfUP5cWV
Content-Type: text/plain

data:image/png;base64,iVBORw0KGgo...
-> 200, the log entry with "img"; the module finishes with result REVIEW about 30 s later
```

## Inji Certify API (`inji_certify.py`)

Base `https://certify.inji.test:18450` (the issuer identifier; APIs under `/v1/certify`). Certify's admin APIs report
many errors as HTTP 200 with `{"response": null, "errors": [...]}`; the client checks the body, not only the status.

| Call | Used for |
|---|---|
| `GET /.well-known/openid-credential-issuer` | readiness |
| `GET /.well-known/oauth-authorization-server` | the TLS proxy's `X-Harness-Shim` header, recorded in `results.json` notes |
| `GET /v1/certify/credential-configurations/{id}` | does the plan's configuration exist (`seed`) |
| `POST /v1/certify/credential-configurations` | create it (`seed`; `vcTemplate` base64-encoded JSON) |
| `POST /v1/certify/pre-authorized-data` | one offer per handoff: `credential_configuration_id`, `claims`, `tx_code`, `expires_in` |

Example offer request and answer (2026-10-14):

```text
POST /v1/certify/pre-authorized-data
{"credential_configuration_id": "InjiConformanceSdJwtVc",
 "claims": {"fullName": "Asha Test-Farmer", "dateOfBirth": "1990-01-15", "gender": "Female"},
 "tx_code": "482913", "expires_in": 600}
-> 200 {"credential_offer_uri": "openid-credential-offer://?credential_offer_uri=https%3A%2F%2Fcertify.inji.test%3A18450%2Fv1%2Fcertify%2Fcredential-offer-data%2F..."}
```

## Inji Verify API (`inji_verify.py`)

Base `https://verify.inji.test:18451/v1/verify`.

| Call | Used for |
|---|---|
| `GET /actuator/health` | readiness |
| `POST /v2/vp-request` | one authorization request per module: `clientId`, `nonce` (16+ URL-safe characters), `dcqlQuery`, `responseMode` |
| `GET /vp-result/{transactionId}` | Inji Verify's verdict for the evidence image and the review |

Example (default configuration, `redirect_uri` client id, request by value):

```text
POST /v1/verify/v2/vp-request
{"clientId": "redirect_uri:https://verify.inji.test:18451/v1/verify/v2/vp-submission/direct-post",
 "nonce": "...", "dcqlQuery": {"credentials": [{"id": "pid", "format": "dc+sd-jwt", "meta": {"vct_values": ["urn:eudi:pid:1"]}}]},
 "responseMode": "direct_post"}
-> 201 {"transactionId": "txn_...", "requestId": "req_...", "authorizationDetails": {...}, "expiresAt": ...}
GET /v1/verify/vp-result/txn_...
-> 200 {"transactionId": "txn_...", "vpResultStatus": "SUCCESS", "vcResults": [{"vc": "...", "verificationStatus": "VALID"}]}
```

The query string the suite receives is the one `getAuthorizationRequestParams` of the Inji Verify SDK builds
(`inji-verify-sdk`, release-1.0.x `6a6ab3b`), byte for byte; `runner/tests/golden/` compares both with the SDK's own
code when Node.js is installed.
