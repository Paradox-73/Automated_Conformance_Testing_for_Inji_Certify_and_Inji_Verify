# Benchmark and gate

The benchmark says which failures and skips are expected today, and why. The gate fails a run on anything else,
and on an expected problem that no longer happens. Files: `conformance/benchmark/<component>.expected-failures.json`
and `<component>.expected-skips.json`; contract: [conformance/schema/README.md](../conformance/schema/README.md).

## Entry format

The suite's own expected-failures format, so `run-test-plan.py` reads the same files, plus four required fields:

```json
{
  "test-name": "oid4vci-1_0-issuer-fail-unknown-credential-configuration",
  "variant": "*",
  "configuration-filename": "*certify.oid4vci-1_0-issuer.json",
  "current-block": " Verify Credential Endpoint Response",
  "condition": "VCIValidateCredentialErrorResponse",
  "expected-result": "failure",
  "comment": "An unknown credential_configuration_id is answered with error invalid_credential_request ...",
  "owner": "inji",
  "spec": "OID4VCI-1FINAL-8.3.1",
  "issue": "docs/findings/certify-credential-error-codes.md"
}
```

- `test-name`, `configuration-filename`: shell patterns. The file name pattern selects the plan template, so one
  benchmark file serves several configurations (`*verify.oid4vp-1final-verifier.json` and
  `*verify.oid4vp-1final-verifier-x509-san-dns.json`); a run uses only the entries of its configuration.
- `variant`: `"*"` or the variant keys that must match.
- `current-block`: the block title as the suite logs it (some have a leading space), `""` or `"*"`.
- `owner`: `inji` (a gap in Inji, with a finding in `docs/findings/`), `suite` (a suite limitation,
  [suite-limitations.md](suite-limitations.md)) or `environment` (the local set-up).
- `spec`: the requirement id the suite logs. `issue`: the finding draft or an issue URL; `bash scripts/check.sh docs`
  checks that it exists.

## Verdicts

| Suite outcome | Benchmark | Verdict | Gate |
|---|---|---|---|
| PASSED | nothing listed | `conforms` | ok |
| WARNING or FAILED, also INTERRUPTED with result FAILED and a logged failure | every condition listed | `known_gap` | ok |
| the same | a condition not listed | `regression` | fails |
| any | a listed condition did not happen, or a listed skip ran | `stale_benchmark` | fails; warns with `--allow-stale` |
| REVIEW | Inji Verify's verdict as expected, evidence uploaded | `conforms` | ok |
| REVIEW | otherwise | `regression` | fails |
| SKIPPED | listed as expected skip | `not_applicable` | ok |
| SKIPPED | not listed | `regression` | fails |
| not finished (WAITING, NOT_STARTED, INTERRUPTED without a failure, time limit) | any | `regression` | fails |

The haip track never gates (`gating: false`). An entry that matches no module of a whole-plan run, or a gate that
disagrees with `run-test-plan.py`'s exit code for the same files, ends the run with exit 2: the benchmark or the
harness is wrong, not Inji.

## Today's benchmark (2026-10-14)

| Component | Configuration | Expected failures | Expected skips | Gate on the reference run |
|---|---|---|---|---|
| Inji Certify | `certify.oid4vci-1_0-issuer` | 13 (11 owner `inji`, 2 `suite`) | 3 (`inji`, optional features) | 0 regressions, 9 known gaps, 0 stale, 3 not applicable |
| Inji Verify | `verify.oid4vp-1final-verifier` (default) | none | none | 0 regressions, 0 known gaps, 0 stale: all 11 conform |
| Inji Verify | `verify.oid4vp-1final-verifier-x509-san-dns` | 20 (10 `suite`, 10 `inji`) | 1 (`inji`) | 0 regressions, 10 known gaps, 0 stale, 1 not applicable |

## Changing the benchmark

1. Run the plan with `--no-gate` and read the failing conditions in `results.json` (or the HTML report).
2. For an Inji gap, write the finding first ([findings/README.md](findings/README.md)); for a suite problem, add a
   row to [suite-limitations.md](suite-limitations.md).
3. Add the entry with the exact condition and block, then rerun without `--no-gate`: the gate passes and
   `run-test-plan.py` agrees.
4. Re-gate a recorded run without the stack:

<!-- run 2026-10-14 -->
```bash
run/venv/bin/inji-conformance gate --run run/reports/wp10-certify/certify --junit run/junit-certify.xml
```

With one Certify entry removed, the same command exits 1 and names the module and condition (measured 2026-10-14
with the `fail-unknown-credential-identifier` entry removed: `regression:
oid4vci-1_0-issuer-fail-unknown-credential-identifier: result FAILED: not in the benchmark:
VCIValidateCredentialErrorResponse`).
