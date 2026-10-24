# Deck outline

The slides of `PS01-Inji-Conformance-Harness.pptx`, 13 slides. Every number on a slide comes from
[test-report.md](../test-report.md) (runs of 2026-10-14 to 2026-10-19).

1. **Title**: Inji conformance harness. Automated OpenID conformance testing for Inji Certify and Inji Verify, with no
   person in the loop. Team Badmosip, MOSIP Decode 2026, problem statement 01.
2. **The problem**: the suite waits for a person (offers, transaction codes, requests, screenshots); results stay
   outside Inji's test reports; no gate in CI; as served, 13 of 15 issuer modules stop at the first check (TC-13).
3. **Target audience**: Inji release teams, countries and integrators, QA teams.
4. **The solution**: `./run-full-stack-conformance.sh`, the handoff responder, the benchmark gate, the reports.
   Screenshot of the consolidated report.
5. **Architecture**: one Docker Compose project; the test side (runner, suite, testrigs, MinIO, pki-init) and the
   systems under test behind the TLS proxy. Source: `docs/diagrams/components.svg`.
6. **Technology stack**: Python 3.12, Bash, Java 21; httpx, Jinja2, jsonschema, Pillow, pytest, ruff, shellcheck,
   TestNG, Maven; the suite release-v5.3.1, Docker Compose v2, PostgreSQL, MongoDB, nginx, MinIO, GitHub Actions.
7. **Live demo flow**: start, handoffs, report, testrigs, break it, gate. Screenshots of the failed gate and the run
   diff; the link to the demo video.
8. **Measured results**: 11 of 11 Inji Verify modules conform; 15 of 15 Inji Certify modules complete (3 passed,
   9 known gaps, 3 not applicable); 0 regressions; 728 s from a fresh clone; 4 green hosted workflow runs; 10 findings.
9. **Impact**: who benefits; 5 handoff kinds automated, 26 modules and 26 TestNG rows per command, 728 s from clone to
   verdict.
10. **What is new**: Inji Verify's own verdict as the screenshot, every accepted failure written down, results in
    Inji's own tools, callable from Inji release pipelines.
11. **Limits**: the TLS proxy adds `authorization_endpoint` to Certify's metadata; Verify's default client id scheme;
    the HAIP track is readiness only; not run yet: `workflow_call` from an Inji repository, fresh clones on macOS and
    Linux; the findings are drafts.
12. **Roadmap**: file the findings, add the caller workflow to Inji release pipelines, close the HAIP gaps,
    self-certification.
13. **Team**: Kanav, Ivan, Sodhi, Nikunj; the repository link.
