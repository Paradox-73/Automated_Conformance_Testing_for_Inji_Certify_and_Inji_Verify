# Deck outline

Ten slides. Every number on a slide comes from [test-report.md](../test-report.md) (2026-10-14).

1. **Title**: Automated OpenID conformance testing for Inji Certify and Inji Verify. Team Badmosip, MOSIP Decode 2026,
   problem statement 01.
2. **The problem**: the OpenID Foundation suite needs a person to hand it offers, codes, requests and screenshots;
   results are not in the Inji test reports; no gate in CI.
3. **What we built**: one command (`run-full-stack-conformance.sh`), Docker Compose stack, runner on the suite's own
   `run-test-plan.py`, handoff responder, benchmark gate, TestNG rows in both api-testrigs, MinIO upload, HTML report,
   badge, diff, GitHub Actions workflow. Diagram: `docs/diagrams/components.svg`.
4. **How a test runs without a person**: the two sequence diagrams (`sequence-issuer.svg`, `sequence-verifier.svg`).
5. **Results**: Inji Verify 11 of 11 modules conform (default configuration); Inji Certify 15 of 15 modules complete,
   3 pass, 9 known gaps, 3 not applicable; full stack in 250 s with testrigs; peak memory 1.6 GiB.
6. **The gate**: verdict table; one benchmark entry per accepted failure with owner, clause, finding; cross-check
   with the suite's own analysis; demo of the injected regression (exit 1, three modules named, diff exit 16).
7. **What we found in Inji**: the ten findings ([findings/README.md](../findings/README.md)): metadata without
   `authorization_endpoint`, unknown request parameters rejected, proof `iss`, error codes, null metadata fields,
   EdDSA-only request signing.
8. **Robustness**: rerun gives the same verdicts; Inji Verify stopped mid-run, suite restarted, port in use, serial
   and parallel agree.
9. **Certification readiness**: the HAIP readiness track and the ranked gaps
   ([certification-readiness.md](../certification-readiness.md)).
10. **How to use it**: quick start from the README, CI for Inji release pipelines
    (`.github/examples/inji-release-caller.yml`), the repository link.
