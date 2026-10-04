# Report, badge and run diff

Package `inji_conformance.report`: the `inji-conformance report` and `inji-conformance diff` subcommands. It reads
the results files and run manifests the runner writes (the contract in
[`conformance/schema/`](../../../../conformance/schema/README.md)) and turns them into pages a person reads: one
consolidated HTML report, a status badge, and a comparison of two runs. It never changes a verdict; the runner
decides each module's verdict once and the report only lays it out.

Lane: delivery. Layout drawn first in [`docs/design/report-wireframe.svg`](../../../../docs/design/report-wireframe.svg);
the design rules are in [`docs/design/README.md`](../../../../docs/design/README.md).

## Commands

```text
inji-conformance report --run DIR [--run DIR] [--combined] [--compare PREV] --out DIR
inji-conformance diff A B [--out DIR] [--json FILE] [--strict]
```

`--run` and `A`/`B` accept a run folder (holds `manifest.json`), a component folder (holds `results.json`) or a
`results.json` file. `--run` may be repeated to report separate component runs together, for example the Inji
Certify and Inji Verify jobs of one CI pipeline.

| Option | Effect |
|---|---|
| `--combined` | Consolidated cross-component report; exit 2 when the runs do not hold both Inji Certify and Inji Verify results |
| `--compare PREV` | Compare with an earlier run: adds a "Changes since run" box to the report and writes `diff.html` |
| `--out DIR` | Output folder; created when missing. Files are written through a temporary file and renamed, so a reader never sees half a page |
| `diff --out DIR` | Also write `diff.html` |
| `diff --json FILE` | Also write the differences as JSON (for CI scripts) |
| `diff --strict` | Exit 1 only when B has a regression that A did not have |

Output of `report`:

| File | Content |
|---|---|
| `summary.html` | The consolidated report: run header, per-component cards, filterable module table |
| `badge.svg` | Label "conformance" and per-component counts, for example `certify 10 ok, 1 gap \| verify 10 ok, 1 gap` |
| `summary.md` | The same counts as a Markdown table, for a GitHub Actions job summary or a pull request comment |
| `diff.html` | Only with `--compare`: what changed since the earlier run |

Exit codes:

| Command | 0 | 1 | 2 | 16 |
|---|---|---|---|---|
| `report` | files written (whatever the gate says) | | a run cannot be loaded, or `--combined` without both components | |
| `diff` | same verdicts | `--strict` and B has a new regression | a run cannot be loaded | the runs differ |

`diff` exits 16 for any difference (the convention of the suite's own `compare-results.py`); with `--strict` it
exits 0 for differences that are not new regressions, such as a fixed module or a new known gap.

Example from the repository root, with the test fixtures (2026-10-04):

```text
$ inji-conformance diff runner/tests/report/fixtures/run-a runner/tests/report/fixtures/run-b
diff A 20261004T191000Z-1a2b3c4 -> B 20261003T101500Z-9f8e7d6
changed  certify  oid4vci-1_0-issuer-happy-flow: conforms (PASSED) -> regression (FAILED); new failing condition EnsureHttpStatusCodeIs200 (FAILURE); NEW REGRESSION
changed  verify   oid4vp-1final-verifier-invalid-kb-jwt-nonce: conforms (REVIEW) -> regression (REVIEW); NEW REGRESSION
changed  certify  oid4vci-1_0-issuer-fail-unknown-credential-configuration: known_gap (FAILED) -> stale_benchmark (PASSED); no longer failing VCIValidateCredentialErrorResponse (FAILURE)
removed  verify   oid4vp-1final-verifier-request-uri-fetched-twice: conforms (PASSED) -> absent
context  harness commit: 1a2b3c4 -> 9f8e7d6
context  verify-service commit: ad3595f -> 0bd41e2
context  verify target commit: ad3595f -> 0bd41e2
result: changed; 3 changed, 0 added, 1 removed, 22 unchanged; 2 new regressions, 0 fixed
$ echo $?
16
```

## What the report shows

- **Header**: run id, mode (combined or component), track, start and end time, the overall gate as icon plus word,
  the badge.
- **Run**: totals per verdict over every module; harness commit (and whether the checkout had uncommitted changes),
  runner version, suite version and URL, command line, host; a table of every container image with its registry
  digest and its source commit label.
- **Changes since run** (with `--compare`): counts, each new regression and each fix with a link to its row, and a
  link to `diff.html`.
- **Components**: one card per component with the five verdict counts, gate, track, target URL and commit, suite
  version, module count, wall time and the plan export zip.
- **Modules**: one row per module, regressions first. Filters by component, verdict and free text (module name or
  failing condition), with a live count for screen readers. Each row links to the module's **live suite log**
  (works while the suite runs) and to the **extracted HTML export** in the run folder (works after the containers
  are gone). A module's button opens its details: description, why the verdict, failing conditions with block,
  message and requirement, benchmark entries with owner, specification and issue, the REVIEW outcome with the
  evidence image, and every handoff with HTTP status and time.

## How a module changes in `diff`

Modules are matched by component and module name; the suite's test ids differ on every run. A module counts as
changed when its verdict, its suite status or result, or its set of failing conditions (condition class plus
severity) differs. Durations, test ids and links never count, so two runs of the same code compare as the same. A
*new regression* is a module that is `regression` in B and was something else in A (or absent). Differences in what
ran (harness commit, image digests and commit labels, suite version, plan and variant, target commit) are listed as
context; they explain a change but never cause one.

## Safety

- The rendered suite configuration (`plan.config_file`) holds the test clients' private keys. The report never
  opens it and never prints its path.
- Every string a template prints passes through `redact.redact` (the template engine's `finalize` hook) and HTML
  escaping. It removes PEM private keys, private JSON Web Key members (`d`, `p`, `q`, `dp`, `dq`, `qi`, `k`) and
  `client_secret`, `password`, `access_token` and `refresh_token` values in query strings, because a failing
  condition's message can quote a request.
- Only absolute `http` and `https` URLs become links; any other scheme from a results file is printed as text or
  dropped.

## Accessibility and themes

- Status is an icon of its own shape plus the word, never colour alone (table in `docs/design/README.md`).
- Text colours meet WCAG 2.1 AA (4.5:1) on both backgrounds of both themes; `tests/report/test_report_html.py`
  computes every ratio from `assets/report.css`, and `test_report_badge.py` does the same for the badge colours.
- The theme follows the system setting; the theme button cycles automatic, light and dark.
- Without script the page is complete: every detail row is shown, and the filters and theme button stay hidden
  because they would do nothing.
- `npx --yes html-validate summary.html diff.html` reports 0 errors (2026-10-04, html-validate's recommended rules).

## Code layout

| File | Role |
|---|---|
| `commands.py` | Argument definitions, `run_report`, `run_diff`, `summary.md`, atomic file writes |
| `runs.py` | Loads and validates run folders and results files; combines component runs |
| `diff.py` | Module-by-module comparison, context changes, exit codes, text output |
| `html.py` | View objects for the pages, link building, the Jinja2 environment, `render_summary`, `render_diff` |
| `badge.py` | Badge text, colour and SVG |
| `redact.py` | Key and credential filter for free text |
| `templates/` | `summary.html.j2`, `diff.html.j2`, shared `_macros.html.j2` (icons, verdict and gate labels, head, footer) |
| `assets/` | `report.css` (colour tokens for both themes) and `report.js` (filters, row toggles, theme), inlined into each page |

## Tests

`runner/tests/report/`, run by `bash scripts/check.sh runner`:

- `fixtures/run-a` (gate passed) and `fixtures/run-b` (an earlier run, gate failed), built from the contract
  examples by `fixtures/build_fixtures.py`; neither is a measured run;
- HTML snapshots in `snapshots/` (rewrite after an intended change with
  `INJI_CONFORMANCE_UPDATE_SNAPSHOTS=1 pytest runner/tests/report`, then review the diff of the snapshot files);
- badge text and colours, diff cases and exit codes, redaction, contrast ratios, the commands end to end.
