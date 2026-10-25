# API reference

This page lists every interface the harness offers or uses, with one example each. Detail stays in the pages linked
from each section.

| Interface | Kind | Detail |
|---|---|---|
| Entry scripts and `inji-conformance` | command line | [reference/cli.md](reference/cli.md) |
| Exit codes | process status | [reference/cli.md](reference/cli.md#exit-codes) |
| `manifest.json` and `results.json` | files the runner writes | [reference/results-schema.md](reference/results-schema.md), [conformance/schema/README.md](../conformance/schema/README.md) |
| Conformance suite REST API | HTTP the runner calls | [api-automation.md](api-automation.md#conformance-suite-api-suitepy) |
| Inji Certify and Inji Verify REST API | HTTP the runner calls | [api-automation.md](api-automation.md) |
| `full-stack-conformance.yml` | GitHub Actions `workflow_call` | [ci.md](ci.md) |

## Command line

Run one component, the gate is the exit code:

```text
./run-conformance.sh --component certify
./run-conformance.sh --combined --serial
inji-conformance gate --run run/reports/<run id> --junit gate.xml
inji-conformance diff run/reports/<previous run id> run/reports/<run id> --strict
inji-conformance validate run/reports/<run id>/manifest.json run/reports/<run id>/certify/results.json
```

Subcommands of `inji-conformance`: `run`, `seed`, `gate`, `report`, `diff`, `validate`. Options and the full table
are in [reference/cli.md](reference/cli.md).

Exit codes: 0 passed, 1 regression or stale benchmark entry, 2 usage, 3 environment, 4 time limit, 5 harness bug,
16 `diff` found differences. Only 1 says something about Inji's conformance, so a CI job can retry on 3 and 5. The
one full table is in [reference/cli.md](reference/cli.md#exit-codes).

## Files the runner writes

One run folder holds `manifest.json` (what ran) and one `<component>/results.json` per component. Both are checked
against the JSON Schemas in `conformance/schema/` (`run-manifest.schema.json`, `results.schema.json`,
`benchmark.schema.json`). Complete files are in `conformance/schema/examples/`.

`results.json`, shortened (`run 20261013T212108Z-6bdc7f`, Inji Certify):

```json
{
  "schema_version": "1",
  "run_id": "20261013T212108Z-6bdc7f",
  "component": "certify",
  "track": "gate",
  "gating": true,
  "target": { "base_url": "https://certify.inji.test:18450" },
  "plan": { "name": "oid4vci-1_0-issuer-test-plan", "id": "OS9kh10wgRy9I" },
  "modules": [
    {
      "name": "oid4vci-1_0-issuer-metadata-test",
      "status": "FINISHED",
      "result": "FAILED",
      "verdict": "known_gap",
      "failures": [{ "condition": "VCICredentialIssuerMetadataValidation", "severity": "FAILURE", "expected": true }]
    }
  ],
  "summary": { "total": 15, "conforms": 3, "known_gap": 9, "regression": 0, "not_applicable": 3, "stale_benchmark": 0 },
  "gate": { "passed": true, "exit_code": 0, "messages": ["gate: 0 regressions, 9 known gaps, 0 stale, 3 not applicable"] }
}
```

`manifest.json` holds `run_id`, `mode`, `track`, `started_at`, `finished_at`, `wall_time_s`, `command`, `harness`
(git commit), `suite`, `images[]`, `components[]`, `gate` and `host`. Field by field:
[reference/results-schema.md](reference/results-schema.md).

## HTTP calls the runner makes

The runner starts the suite's own `run-test-plan.py` and also calls the suite and the two Inji components directly.
The suite runs in its `dev` profile, so no API token is needed.

| Target | Calls |
|---|---|
| Conformance suite, `https://localhost.emobix.co.uk:18443` | `GET /api/server`, `GET /api/runner/running`, `GET`/`POST /api/runner/{id}`, `POST /api/runner/browser/{id}/visit?url=`, `GET /api/info/{id}`, `GET /api/log/{id}`, `GET /api/plan/{id}`, `GET /api/plan/exporthtml/{id}` |
| Inji Certify, `https://certify.inji.test:18450` | `GET /.well-known/openid-credential-issuer`, `GET`/`POST /v1/certify/credential-configurations`, `POST /v1/certify/pre-authorized-data` |
| Inji Verify, `https://verify.inji.test:18451/v1/verify` | `GET /actuator/health`, `POST /v2/vp-request`, `GET /vp-result/{transactionId}` |

Offer request to Inji Certify and its answer:

```text
POST /v1/certify/pre-authorized-data
{"credential_configuration_id": "InjiConformanceSdJwtVc",
 "claims": {"fullName": "Asha Test-Farmer", "dateOfBirth": "1990-01-15", "gender": "Female"},
 "tx_code": "482913", "expires_in": 600}
-> 200 {"credential_offer_uri": "openid-credential-offer://?credential_offer_uri=https%3A%2F%2Fcertify.inji.test%3A18450%2F..."}
```

Verification request to Inji Verify and its result:

```text
POST /v1/verify/v2/vp-request
{"clientId": "redirect_uri:https://verify.inji.test:18451/v1/verify/v2/vp-submission/direct-post",
 "nonce": "...", "dcqlQuery": {"credentials": [{"id": "pid", "format": "dc+sd-jwt"}]}, "responseMode": "direct_post"}
-> 201 {"transactionId": "txn_...", "requestId": "req_..."}
GET /v1/verify/vp-result/txn_...
-> 200 {"transactionId": "txn_...", "vpResultStatus": "SUCCESS", "vcResults": [{"verificationStatus": "VALID"}]}
```

All calls with their purpose: [api-automation.md](api-automation.md).

## GitHub Actions workflow

`.github/workflows/full-stack-conformance.yml` runs on pushes to `main` and pull requests that change more than
docs, release, a weekly schedule, manual dispatch and `workflow_call`. An Inji repository calls it after a release build:

```yaml
jobs:
  conformance:
    uses: Paradox-73/Automated_Conformance_Testing_for_Inji_Certify_and_Inji_Verify/.github/workflows/full-stack-conformance.yml@v1.0.0
    with:
      harness_ref: v1.0.0
      component: certify
      track: gate
      strict: true
      certify_image: injistackqa/inji-certify-with-plugins@sha256:...
```

| Input | Type | Default | Meaning |
|---|---|---|---|
| `component` | string | `both` | `both`, `certify` or `verify` |
| `track` | string | `gate` | `gate` (1.0 Final plans, gating) or `haip` (readiness, never gating) |
| `strict` | boolean | `true` | stale benchmark entries fail the run |
| `certify_image` | string | empty | Inji Certify image override |
| `verify_image` | string | empty | Inji Verify image override |
| `harness_repository` | string | this repository | repository every job checks out |
| `harness_ref` | string | `main` | branch, tag or commit of the harness; use the ref of the `uses:` line |
| `full_stack` | boolean | `true` | also run the job that starts from scratch |

A complete caller is `.github/examples/inji-release-caller.yml`. More in [ci.md](ci.md).
