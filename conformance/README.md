# conformance

Data that defines a conformance run: which suite test plans run with which options, which results are expected,
and the JSON Schemas of the files the runner reads and writes.

Lane: runner. Status on 2026-10-04: `schema/` holds the results and benchmark contract
([`schema/README.md`](schema/README.md)); `plans/` holds the Inji Verify plan template and the Inji Certify
plan template, the second not yet run against a live stack ([`plans/README.md`](plans/README.md)); `benchmark/`
is still empty.

## Planned contents

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
