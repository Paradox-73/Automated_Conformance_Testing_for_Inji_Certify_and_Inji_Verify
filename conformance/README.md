# conformance

Data that defines a conformance run: which suite test plans run with which options, which results are expected,
and the JSON Schemas of the files the runner reads and writes.

`schema/` holds the results and benchmark contract ([`schema/README.md`](schema/README.md)); `plans/` holds the plan
templates of both components and the HAIP readiness track ([`plans/README.md`](plans/README.md)); `benchmark/` holds
the expected failures and skips ([docs/benchmark.md](../docs/benchmark.md)).

## Gate variant of the issuer plan

Decision (2026-10-14): the gate runs the issuer plan with `sender_constrain=dpop`.

| Variant | Command | Conditions reached |
|---|---|---|
| `dpop` | `inji-conformance run --component certify --no-gate` | 15 of 15 modules complete; flows stop at the credential endpoint (unknown parameter, proof `iss`, error codes); 3 negative modules pass |
| `mtls` | the same with `--variant sender_constrain=mtls` | the same 15 outcomes and conditions |

Neither variant reaches credential issuance, and the credential requests fail before Inji Certify checks the
sender constraint, so the variants cannot be told apart yet. `dpop` stays, because Inji Certify has no mTLS
support and its access tokens carry no `cnf` (measured with a probe on 2026-10-04): once issuance works, the DPoP
variant is the one that shows the binding gap. Evidence: [docs/test-report.md](../docs/test-report.md) (TC-12).

## Contents

| Path | Purpose |
|---|---|
| `plans/` | JSON plan templates for the suite: the OpenID4VCI 1.0 issuer plan for Inji Certify and the OpenID4VP 1.0 verifier plan for Inji Verify, with their variants (the options that select the protocol flavour) |
| `benchmark/` | Expected failures and skips, each with a reason, an owner and a link; the gate fails on anything not listed |
| `schema/` | JSON Schemas of the results file, the run manifest and the benchmark |
| `schema/examples/` | Example files; `bash scripts/check.sh runner` validates them |

## Example naming

- `*.invalid.json`: must be rejected by `inji-conformance validate`. Keep at least one, so the check proves the
  validator rejects bad input.
- Any other `*.json`, for example `results-verify.example.json`: must validate.
