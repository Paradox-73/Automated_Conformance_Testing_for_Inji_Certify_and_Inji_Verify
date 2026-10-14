# Results file and run manifest

The runner writes one `results.json` per component and one `manifest.json` per run folder. The JSON Schemas and
every rule beyond them are in [conformance/schema/README.md](../../conformance/schema/README.md); this page is a
reader's guide.

## Run folder

```text
run/reports/<run id>/
  manifest.json                       what ran: commit, images, wall time per plan, gate
  images.json                         the containers' images and digests (written by run-conformance.sh)
  <component>/results.json            one per component
  <component>/config/<template>.json  the rendered suite configuration, placeholders instead of keys
  <component>/benchmark/              the benchmark entries run-test-plan.py was given
  <component>/exports/                the suite's JSON export zip, the HTML export zip, and html/ extracted
  <component>/evidence/               Inji Verify only: the verdict images uploaded for REVIEW modules
  <component>/logs/                   run-test-plan.log, handoffs.jsonl
  report/                             summary.html, badge.svg, summary.md (diff.html with --compare)
  testrig/<component>/                the api-testrig EmailableReport and report.txt
  logs/                               compose-up, runner, testrig, report and compose logs
```

The exports (the zips and the extracted HTML pages) hold the suite configuration with its private keys: never commit or upload them. The committed evidence in
`docs/evidence/` keeps only `results.json`, the manifest, the report and badge.

## results.json (version 1)

| Field | Content |
|---|---|
| `run_id`, `component`, `track`, `gating` | which run; `gating` is false on the haip track |
| `suite`, `target` | suite URL and version; Inji's URL |
| `plan` | plan name, variant, suite plan id, rendered config file, export |
| `modules[]` | per module: `name`, `test_id`, `status`, `result`, `verdict`, `verdict_reason`, `failures[]` (condition, severity, message, block, requirement ids, `expected`), `benchmark[]` (the entries that apply, `matched`), `review` (expected and observed verdict, evidence image), `handoffs[]` (kind, HTTP status, time, detail, error), `links` (suite log, HTML export page), `duration_s` |
| `summary` | counts per verdict |
| `gate` | `passed`, `exit_code`, `allow_stale`, `benchmark_files`, `messages` (the first is `gate: <n> regressions, <n> known gaps, <n> stale`) |
| `notes` | anything a reader must know, for example the TLS proxy's change to Inji Certify's metadata, failed responder polls |

Check a file:

<!-- run 2026-10-14 -->
```bash
run/venv/bin/inji-conformance validate run/reports/<run id>/manifest.json run/reports/<run id>/certify/results.json
```

On Windows the command is `run/venv/Scripts/inji-conformance`.

## manifest.json

`run_id`, `mode` (component or combined), `track`, `parallel`, `started_at`, `finished_at`, `wall_time_s`,
`command`, `harness` (git commit, dirty flag, runner version), `suite`, `images[]` (service, image, digest, source
commit label), `components[]` (plan, results path, start, end, wall time, exit code), `gate`, `host`.
