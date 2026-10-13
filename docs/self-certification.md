# Self-certification with the OpenID Foundation

How Inji Certify and Inji Verify could be submitted for OpenID certification once their plans pass, and how far
they are today. The OpenID Foundation's certification program accepts the logs of a certification-profile plan run
on the hosted suite (`https://www.certification.openid.net`) with every module passed or with accepted warnings,
together with a signed declaration of conformance.

## What the harness gives you

- The same plans the hosted suite runs, with the same variants, on a local copy of the suite (release-v5.3.1).
- Per module: result, failing conditions with requirement ids, the suite log and the suite's HTML export
  (`<run>/<component>/exports/`), which is the evidence a certification submission contains.
- A benchmark that lists, with a finding per entry, everything that still fails.

## Steps for a submission

1. Fix the findings in [findings/README.md](findings/README.md) until `./run-conformance.sh --combined` passes with
   an empty benchmark (no `known_gap`, no `not_applicable` entries owned by `inji`).
2. Run the certification-profile plans: today those are the HAIP plans (`--track haip`); the plain OpenID4VCI 1.0
   and OpenID4VP 1.0 plans are marked by the suite as not part of the certification program
   ("alpha tests ... use the HAIP verifier plan to certify").
3. Run the same plan on the hosted suite against a publicly reachable deployment of the Inji component (the hosted
   suite cannot reach `*.inji.test`), with the configuration the local run used (`<run>/<component>/config/`,
   with real keys instead of the placeholders).
4. In the hosted suite, use "Publish for certification" on the plan, download the certification package and send
   it with the signed declaration, as the OpenID Foundation's certification instructions describe.

## Where Inji stands (2026-10-14)

Not ready for submission: both components need changes first. The HAIP readiness run and the gaps ranked by
effort are in [certification-readiness.md](certification-readiness.md). The suite refuses a certification package
for a plan with failures, and both HAIP plans fail today.
