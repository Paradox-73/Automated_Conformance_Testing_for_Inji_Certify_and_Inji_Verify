# Results and benchmark contract

JSON Schemas (draft 2020-12) of the three kinds of file the harness passes between its parts. The runner writes
them; the gate, the HTML report, CI and the TestNG bridge in the testrigs read them. Readers trust a file that
`inji-conformance validate` accepts and never re-derive a verdict.

| Schema | File it describes | Written by | Read by |
|---|---|---|---|
| [`results.schema.json`](results.schema.json) | `results.json`, one per component and run | runner | gate, report, diff, CI, TestNG bridge |
| [`run-manifest.schema.json`](run-manifest.schema.json) | `manifest.json`, one per run folder | entry scripts and runner | report, diff |
| [`benchmark.schema.json`](benchmark.schema.json) | `<component>.expected-failures.json`, `<component>.expected-skips.json` | people, in review | runner (gate), `run-test-plan.py` |

The schemas refer to each other by `$id` (`urn:inji-conformance:schema:<name>:v1`), so a validator needs all three
loaded. `inji_conformance.model` does that and also checks the rules listed under
[Rules beyond the schema](#rules-beyond-the-schema).

## Validate a file

```bash
inji-conformance validate path/to/results.json [more files...]
inji-conformance validate --kind expected-failures my-benchmark.json   # when the file name does not say
```

- One line per file: `validate <file name>: valid (...)`, or `invalid (...)` followed by one indented line per
  problem with its JSONPath, for example `$.modules[0].verdict: 'passed' is not one of [...]`.
- The kind comes from the file name (`results*`, `*manifest*`, `*expected-failures*`, `*expected-skips*`), then
  from the content; `--kind` overrides both.
- Exit status: 0 every file is valid, 1 at least one is invalid, 2 a file is missing or its kind is unknown.
- The schema folder is found by walking up from the installed package to `conformance/schema`. Where the package is
  installed away from a checkout (a container image), set `INJI_CONFORMANCE_SCHEMA_DIR` to this folder.

## results.json, version 1

Top level: `schema_version` (`"1"`), `run_id` (UTC start time plus a suffix, for example
`20261004T193000Z-1a2b3c4`), `component` (`certify` or `verify`), `track` (`gate` or `haip`), `gating` (false for
the haip readiness track, which never changes the exit code), `suite`, `target`, `plan`, `modules`, `summary`,
`gate`, and optionally `started_at`, `finished_at`, `notes`.

Each module carries:

| Field | Meaning |
|---|---|
| `name`, `test_id` | Suite module name and test id (`null` when it never started) |
| `status`, `result` | Last suite status (`NOT_STARTED` is the harness's own value) and suite result (`null` until finished) |
| `verdict`, `verdict_reason` | The harness verdict (table below) and, for `regression` and `stale_benchmark`, one line on why |
| `failures` | Every FAILURE and WARNING log entry: condition, severity, message, block, requirement ids, and `expected` when a benchmark entry lists it |
| `benchmark` | The benchmark entries that apply, with `matched: false` for a listed problem that did not happen |
| `review` | For a module the suite leaves in REVIEW: the verdict Inji Verify showed, the one the module expects, and the evidence image |
| `handoffs` | Each step the harness performed where the suite waits (authorization request, credential offer, evidence upload...), with HTTP status and time |
| `links` | Live suite log URL, and the extracted HTML export relative to the run folder (works after teardown) |

Paths in a results file or manifest are relative to the run folder: forward slashes, no leading slash, no drive
letter, no `..`. Suite configurations hold private keys, so a results file names the rendered configuration but
never embeds it.

### Verdicts

One table drives the gate, the report and the TestNG rows. The runner applies it once; readers map the `verdict`
field.

| Suite outcome | Benchmark | Verdict | Gate |
|---|---|---|---|
| PASSED | not listed | `conforms` | ok |
| PASSED, or a listed condition did not occur | listed as expected failure | `stale_benchmark` | fails; warns with `--allow-stale` |
| WARNING or FAILED | every warning or failing condition listed | `known_gap` | ok |
| WARNING or FAILED | any condition not listed | `regression` | fails |
| REVIEW | Inji Verify's verdict matches the module's expectation, evidence image present | `conforms` | ok |
| REVIEW | verdict differs or no evidence | `regression` | fails |
| SKIPPED | listed as expected skip | `not_applicable` | ok |
| SKIPPED | not listed | `regression` | fails |
| INTERRUPTED, timeout, never started | any | `regression` | fails |

## Benchmark files

The OpenID conformance suite's own expected-failures and expected-skips format, so
`run-test-plan.py --expected-failures-file` and `--expected-skips-file` read the same files, plus four required
fields that make every accepted problem justified and traceable:

| Field | Rule |
|---|---|
| `comment` | Why the result is expected, at least 10 characters |
| `owner` | `inji` (a gap in Inji), `suite` (a problem in the conformance suite) or `environment` (a limit of the local set-up) |
| `spec` | The clause the result is about, as the suite names requirements, for example `OID4VP-1FINAL-5.10` |
| `issue` | A repository path to an issue draft ending in `.md` (for example `docs/findings/<name>.md`) or an `https` URL of a filed issue |

The suite fields keep their suite meaning: `test-name` and `configuration-filename` are shell-style patterns
(`fnmatch`); `variant` is `"*"` or an object whose listed keys must match; `current-block` is the block title, `""`
for none or `"*"` for any; `condition` is the condition class name; `expected-result` is `failure` or `warning`.
Use a wildcard `configuration-filename` such as `*verify.oid4vp-1final-verifier*.json`, because the configuration is
rendered into a different run folder each time. An expected-skips entry has no condition fields.

## Rules beyond the schema

`inji-conformance validate` rejects a file that passes the schema but breaks one of these rules:

- results: module names are unique; `summary` counts equal the counts of the modules' verdicts; `gate.passed` is
  true exactly when `gate.exit_code` is 0; a gating run with a regression (or a stale entry without
  `allow_stale`) has not passed, and exit code 1 needs such a module; a non-gating run never exits 1;
  `finished_at` is not before `started_at`.
- results, per module (the verdict table): a module that did not finish is a regression; `conforms` needs PASSED,
  or REVIEW with a matching review and an evidence image; `known_gap` needs FAILED or WARNING with every failure
  listed by a matched expected-failure entry; `not_applicable` needs a matched expected-skip entry; an unlisted
  failure always makes a regression; `stale_benchmark` needs an unmatched entry; `regression` and
  `stale_benchmark` carry a `verdict_reason`.
- run manifest: components are unique; `component` mode has one component and `combined` mode has both; the gate
  has not passed when a component exited non-zero.
- benchmark: no two entries share the suite's duplicate key (test name, variant, configuration file name,
  condition, block). `run-test-plan.py` only warns about duplicates; here they are an error, so files stay clean.

## Examples

`examples/` holds hand-written examples of the contract, not output of measured runs. Their module lists are what
the suite creates for the chosen plan variants; results, messages and benchmark entries are illustrative.
`bash scripts/check.sh runner` validates every example, and requires each `*.invalid.json` to be rejected.

| File | Shows |
|---|---|
| `results-certify.example.json` | Issuer plan, 15 modules (variant set listed by the suite on 2026-10-04): conforms, known gap, not applicable; gate passed |
| `results-certify-regression.example.json` | The same with a regression in the happy flow and a stale benchmark entry; gate failed |
| `results-verify.example.json` | Verifier plan, 11 modules for `x509_san_dns` and `request_uri_signed` (not yet confirmed by a created plan); REVIEW modules with evidence; gate passed |
| `results-verify-regression.example.json` | The same where Inji Verify accepts a presentation it should reject; gate failed |
| `run-manifest.example.json` | A combined run of both components |
| `certify.expected-failures.example.json`, `certify.expected-skips.example.json`, `verify.expected-failures.example.json`, `verify.expected-skips.example.json` | Benchmark files the results examples refer to |
| `results-unknown-verdict.invalid.json` | Rejected by the schema: a verdict that does not exist |
| `results-summary-mismatch.invalid.json` | Rejected by the rules beyond the schema: summary counts that do not match the modules |
| `certify-missing-owner.expected-failures.invalid.json` | Rejected by the schema: a benchmark entry without `owner` |

## Changing the contract

- Adding an optional field is a compatible change: add it to the schema and to `inji_conformance.model`, and to an
  example so the round-trip test covers it.
- Renaming or removing a field, or changing its meaning, needs `schema_version` `"2"` and a new `$id`, because the
  TestNG bridge and saved results of earlier runs read version 1.
