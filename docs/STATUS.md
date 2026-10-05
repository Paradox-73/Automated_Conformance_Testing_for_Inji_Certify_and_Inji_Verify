# Project status and remaining work

Status of the harness on **2026-10-04 at 20:45 IST**, when work stopped. Deadline: **2026-10-26 23:59 IST**.

| Item | Value |
|---|---|
| Repository | <https://github.com/Paradox-73/Automated_Conformance_Testing_for_Inji_Certify_and_Inji_Verify> |
| `main` | `511baf9df86892cbd9850c24106b09c0d2361908` (2026-10-04 16:52 IST), the same commit as `origin/main` |
| Unfinished work | Branch `feat/issuer-path` continues task WP-08 from the snapshot branch `wip/2026-10-04-stop` (commit `e8a3f7e`, 2026-10-04 20:45 IST). Code, unit tests and READMEs are done; the live acceptance run is open. See the WP-08 card. |

The snapshot branch is on GitHub (pushed 2026-10-04) and is kept only as the starting point of `feat/issuer-path`.

How to work on a task: [CONTRIBUTING.md](../CONTRIBUTING.md). The words used below:

- **Suite**: the OpenID Foundation conformance suite (Java server, MongoDB, nginx). It plays the wallet against
  both Inji components.
- **Plan, module, variant**: a plan is a named list of tests; a module is one test; variants select the protocol
  flavour (for example `sender_constrain=dpop`).
- **WAITING, handoff, responder**: a module is WAITING when the suite waits for the system under test (an offer, an
  authorization request, a screenshot). A handoff is what lets it continue. The handoff responder is the runner's
  thread that does every handoff without a person.
- **Benchmark**: the list of expected failures and skips, each with a written reason. The gate fails on anything
  not on the list.
- **Lane**: one of four work streams (platform, runner, testrig, delivery). Every folder has one owning lane, so
  two people never edit the same files. Table in [How to split the remaining work](#how-to-split-the-remaining-work).
- **`DC`** in older notes means `bash scripts/dc.sh`, the only way to call Docker Compose here.

## All tasks

DONE means the task's acceptance check was run and passed on the date in its commits. PARTIAL means work exists
but the acceptance check was not run. TODO means nothing was started.

| Id | Lane | Title | Depends on | Status | Commits |
|---|---|---|---|---|---|
| WP-01 | platform | Scaffold: layout, lane READMEs, `scripts/check.sh` | - | DONE | `9a4fee1`, `f999769` |
| WP-02 | runner | Import the suite's automation scripts unchanged (release-v5.3.1, MIT) | WP-01 | DONE | `1f7018a`, `8f11a33` |
| WP-03 | testrig | Import the Inji Certify and Inji Verify api-test trees unchanged (Apache-2.0) | WP-01 | DONE | `9d07328`, `f307a88`, `fcecc46` |
| WP-04 | runner | Results and benchmark contract (JSON Schemas, examples, `inji_conformance.model`, CLI skeleton) | WP-01 | DONE | `eb60413`, `a4f601a` |
| WP-05 | platform | Compose v1: suite, Inji Verify, TLS proxy, run-time keys | WP-01 | DONE | `eaac172`, `7d931ba`, `478b318`, `2694161` |
| WP-06 | runner | Walking skeleton: `inji-conformance run --component verify` with the handoff responder | WP-02, WP-04, WP-05 | DONE | `be987eb`, `f1f83e1`, `a707012`, `345ab93` (compose build change inside `7eb88b4`) |
| WP-07 | platform | Compose v2: Inji Certify and MinIO | WP-05 | DONE | `bcd8521`, `7eb88b4`, `2dd30a8` |
| WP-08 | runner | Issuer path: Certify seeding and credential offer handoff | WP-06, WP-07 | PARTIAL | branch `feat/issuer-path` (from `wip/2026-10-04-stop`, `e8a3f7e`), not on `main` |
| WP-09 | runner | Results parser, benchmark gate, checked REVIEW evidence | WP-06, WP-08 | TODO | |
| WP-10 | platform | One-command scripts `run-conformance.sh` and `run-full-stack-conformance.sh` | WP-09, WP-13 | TODO | |
| WP-11 | testrig | TestNG bridge library and the Inji Verify rig integration | WP-03, WP-04 | DONE | `511baf9` |
| WP-12 | testrig | Inji Certify rig integration, MinIO upload, testrig image | WP-09, WP-11 | TODO | |
| WP-13 | delivery | Consolidated HTML report, badge and run diff | WP-04 | DONE | `faad42c`, `fb772ae` |
| WP-14 | runner | Parallel execution and HAIP readiness track | WP-10 | TODO | |
| WP-15 | platform | GitHub Actions workflow `full-stack-conformance.yml` | WP-10, WP-12, WP-13 | TODO | |
| WP-16 | delivery | Documentation set | WP-10, WP-11 | TODO | |
| WP-17 | delivery | Test report, test data and Inji findings | WP-09, WP-12, WP-14, WP-16 | TODO | |
| WP-18 | delivery | Demo script, video and deck material, final README | WP-13, WP-15, WP-16, WP-17 | TODO | |

Longest chain still open: WP-08 -> WP-09 -> WP-10 -> WP-14 -> WP-17 -> WP-18. WP-12 also waits for WP-09.

### What the finished tasks proved (2026-10-04)

- `bash scripts/check.sh all`: eol, secrets and shell PASS (WP-01); runner PASS with ruff clean and 133 tests at the
  end of WP-04, later grown by WP-06 and WP-13.
- `bash compose/smoke.sh verify` PASS: start 34-76 s, peak about 0.9 GiB (WP-05).
  `bash compose/smoke.sh certify reports` PASS: start 134 s, peak about 1.5 GiB (WP-07). Output in
  [compose/README.md](../compose/README.md).
- `inji-conformance run --component verify --modules oid4vp-1final-verifier-happy-flow --no-gate` exit 0: the
  module reached FINISHED (result FAILED, see [open problems](#open-problems-found-by-finished-tasks)) with one
  `authorization_request` handoff answered HTTP 200 (WP-06). Details in [runner/README.md](../runner/README.md).
- Bridge and Inji Verify rig: `mvn ... package` BUILD SUCCESS in 8 min 23 s with 51 JUnit tests;
  `ConformanceRigRunner` on the example results exits 0 with rows `TC_OIDF_VERIFY_01` to `_11`, on the regression
  example exits 1, with no settings exits 0 with one Ignored row (WP-11). Details in
  [testrigs/apitest-commons-conformance/README.md](../testrigs/apitest-commons-conformance/README.md).
- `inji-conformance report` and `diff` on the fixtures in `runner/tests/report/fixtures/`: `summary.html`,
  `badge.svg`, `summary.md`, `diff.html`; `diff` exit 0 for identical runs and 16 for changed runs (WP-13).
  Details in [runner/src/inji_conformance/report/README.md](../runner/src/inji_conformance/report/README.md).

### Open problems found by finished tasks

These are not part of any task card yet. The lane named in the first column fixes them.

| Lane | Problem | Fix |
|---|---|---|
| platform | Inji Verify's `direct-post` answers HTTP 500, so every verifier module fails at the wallet's response. `compose/verify/init.sql` (imported unchanged from inji-verify `6a6ab3b`) has no `vp_submission.response_code` column; the `1.0.x` image (`ad3595f`) needs it, and the upstream `db_scripts` DDL has it. | Add the column in a new commit on top of the import commit. Check: rerun the WP-06 happy-flow command; `EnsureHttpStatusCodeIs200` must no longer fail. |
| platform | `bash scripts/dc.sh down -v` without profiles leaves services started with a profile running, and a later run silently uses that old stack. | Until fixed, always stop with `bash scripts/dc.sh --profile '*' down -v`. Fix: make `scripts/dc.sh` add `--profile '*'` to `down`, with a test in `scripts/tests/test-dc.sh`. |
| runner (WP-09 benchmark), delivery (WP-17 findings) | The verifier happy flow also failed `ValidateRequestObjectSignatureAgainstX5cHeader` (Inji Verify's request-object certificate is self-signed) and warned on `ValidateRequestObjectIssIfPresent` (`iss` differs from `client_id`) and `ValidateDirectPostResponse`. | Inji-side behaviour, not harness bugs: benchmark entries with owner `inji` and finding drafts. |
| runner | The full verifier plan on a busy Docker VM hit a 20-minute limit after 6 of its modules (handoffs took 12-70 s each). | The default limit is now 30 minutes (`--timeout-minutes`); `results.json` is written on timeout (exit 4). Measure a full plan again before setting CI timeouts. |
| runner | The verify example results list 11 modules, assuming the `x509_san_dns`/`request_uri_signed` variant adds `request-uri-fetched-twice`. No full plan has confirmed that yet. | Compare with the first full verifier run. |

## Remaining task cards

Every command below runs in bash (Git Bash on Windows) from the repository root. Container paths: `/reports` in
the `runner` container is `$HARNESS_RUN_DIR/reports` on the host, `/pki` is `$HARNESS_RUN_DIR/pki`. Files named
"created by this task" do not exist yet.

### WP-08 runner: Issuer path (Certify seeding and credential offer handoff). PARTIAL

- **Goal**
  - `inji-conformance seed certify`, idempotent: reads Inji Certify's credential configurations and adds the
    `dc+sd-jwt` one the issuer plan asks for when it is missing. A MOSIP error envelope inside an HTTP 200 counts
    as a failure.
  - `inji-conformance run --component certify` seeds first (unless `--no-seed`), so a fresh stack needs no manual
    step, then runs the suite plan `oid4vci-1_0-issuer-test-plan` against Inji Certify.
  - The responder answers issuer modules: on WAITING with `credential_offer_endpoint` it calls
    `POST /v1/certify/pre-authorized-data`, takes `credential_offer_uri` out of the `openid-credential-offer://`
    URL and calls `GET <credential_offer_endpoint>?credential_offer_uri=<it>`; it answers `tx_code_endpoint` with
    the offer's transaction code; it delivers a new offer each time a module waits again.
  - Run the plan once with `sender_constrain=dpop` and once with `sender_constrain=mtls`, record which conditions
    each reaches, gate on the variant that reaches credential issuance, and write the decision and evidence in
    `conformance/README.md`.
- **Depends on**: WP-06, WP-07 (both DONE).
- **Owns**: `runner/src/inji_conformance/` except `report/`, `runner/tests/` except `report/`,
  `conformance/plans/`, `conformance/README.md`, `runner/README.md`.
- **Acceptance check**

  ```bash
  bash scripts/check.sh runner
  bash scripts/dc.sh --profile tools build runner
  bash scripts/dc.sh --profile certify up -d --wait
  bash scripts/dc.sh run --rm runner sh -c "inji-conformance seed certify && inji-conformance seed certify && inji-conformance run --component certify --no-gate --out /reports/wp08"
  rc=$?; bash scripts/dc.sh --profile '*' down -v; echo "exit $rc"
  ```

  Expected: `check.sh runner` prints PASS; `exit 0`; the second seed prints `already present`;
  `$HARNESS_RUN_DIR/reports/wp08/certify/results.json` lists every module of the created plan with status
  FINISHED, none interrupted or timed out; every module that exposed a `credential_offer_endpoint` has a
  `credential_offer` handoff with an HTTP status below 400. The two metadata modules
  (`VCIIssuerMetadataTest`, `VCIIssuerMetadataSignedTest` in the suite) never ask for an offer.
- **What is on the branch `feat/issuer-path`** (2026-10-04; it starts from the seven files of the snapshot
  branch `wip/2026-10-04-stop`):
  - `conformance/plans/certify.oid4vci-1_0-issuer.json`: variant `fapi_profile=vci`,
    `credential_format=sd_jwt_vc`, `vci_grant_type=pre_authorization_code`,
    `vci_authorization_code_flow_variant=issuer_initiated`, `client_auth_type=private_key_jwt`,
    `sender_constrain=dpop`, `authorization_request_type=simple`, `fapi_request_method=unsigned`,
    `vci_credential_encryption=plain`; alias `inji-certify-${run_id}`; a `seed.credential_configuration` block
    (configuration id `InjiConformanceSdJwtVc`, `vct` `urn:inji-conformance:vct:farmer:1`, key ids
    `CERTIFY_VC_SIGN_EC_R1` / `EC_SECP256R1_SIGN`, ES256, claims `fullName`, `dateOfBirth`, `gender`); a
    `handoff.credential_offer` block (claims, 6-digit transaction code, 600 s expiry).
  - `runner/src/inji_conformance/inji_certify.py`: `CertifyClient`, MOSIP error-envelope check, idempotent
    `seed` (prints `created` or `already present`), `create_offer`, `credential_offer_uri` extraction,
    `new_tx_code`.
  - `runner/src/inji_conformance/keys.py`: fresh P-256 private JWK sets for the suite's two wallet clients
    (`client`, `client2`), written only into the staged `certs-keys/` folder, standard library only.
  - `handoff.py`: `CredentialOfferHandoff` (offer, then transaction code; at most 6 offers per module).
  - `run.py`: `--component certify`, seeding before the run, `cmd_seed`, `--variant NAME=VALUE`, environment
    variable `HARNESS_CERTIFY_URL` (default `https://certify.inji.test:18450`), the `certs_keys` forms.
  - `plans.py`: `certs_keys` forms (`{"from": <file>, "as": "json_string"}`, `{"generate": "p256_jwks"}`), the
    `seed` block with `render_seed`, `with_variant`. `cli.py`: `seed` wired to `cmd_seed`, `run --variant`.
  - Unit tests for all of the above (`runner/tests/test_inji_certify.py`, `test_keys.py`, and new cases in
    `test_handoff.py`, `test_plans.py`, `test_run.py`, `test_cli.py`), and the README updates
    (`runner/README.md`, `conformance/plans/README.md`, `conformance/README.md`).
- **Fixed on the branch after the snapshot** (2026-10-04):
  - The ruff error in `keys.py` and the three `test_cli.py` cases that still expected "not available".
  - Tests wrote into `<repo>/run`: an autouse fixture in `runner/tests/conftest.py` now points
    `HARNESS_RUN_DIR` at pytest's `tmp_path` and clears the other `HARNESS_*` locations for every test, and the
    readiness limit is read when `wait_until_ready` is called, so a test can set it to 0 instead of waiting 120 s.
  - The `seed` block was sent to Inji Certify as written in the template: `credentialConfigKeyId` would have
    been the text `${credential_configuration_id}`, and the `$comment` note was part of the request. Found while
    writing the seeding tests, before any live run. `plans.render_seed` now replaces the variables and drops the
    notes; `vcTemplate` stays as written, because its `${claim}` placeholders are Inji Certify's.
  - While Inji Certify starts, a metadata answer other than HTTP 200 with a JSON object raised `CertifyError`
    out of `wait_until_ready` and ended `seed` and `run` with a traceback. It now counts as "not ready" and is
    asked again until the limit (exit 3).
- **Checked on 2026-10-04 on the branch** (unit level only; nothing was run against a live stack):
  - `bash scripts/check.sh eol secrets runner`: PASS, PASS, PASS (`ruff` clean, `pytest runner/tests` 395
    passed, 9 schema examples valid, 3 invalid examples rejected). Run on Linux (aarch64) with Python 3.12.14;
    `git status --porcelain` showed no run output afterwards.
  - The client code was read against the Inji Certify source at `203b143` (`CredentialConfigController.java`,
    `CredentialConfigurationServiceImpl.java`, `ExceptionHandlerAdvice.java`, `PreAuthorizedCodeController.java`,
    `PreAuthorizedRequest.java`): an unknown configuration id answers HTTP 404 with an envelope, creation
    answers HTTP 201 with `id` and `status`, and the offer request fields and limits match. The suite side
    (which endpoints a module exposes, and when) has only been read from the suite source by the snapshot's
    author and is not confirmed by a run.
- **What remains**
  1. The live acceptance run above, then the same with `--variant sender_constrain=mtls`; write which conditions
     each variant reached and the chosen gate variant in `conformance/README.md`. Expect the first live run to
     find problems the unit tests cannot (plan and variant names, configuration keys, the suite's WAITING
     states); fix them on this branch.
  2. After the live run: replace "not yet run against a live stack" in `runner/README.md` and
     `conformance/plans/README.md` with what was measured, and set this task to DONE with the commit ids.
- **Notes**
  - Inji Certify's admin APIs return many errors as HTTP 200 with `{"response": null, "errors": [...]}`; check
    `errors`, never the status alone.
  - `vcTemplate` must be base64-encoded JSON. A raw JSON string is accepted at creation but fails at issuance with
    `json_processing_error` (measured 2026-10-04).
  - Offer claims must match the configuration's claims exactly; unknown or missing mandatory claims are rejected.
  - Pre-authorized codes are single-use: the multiple-clients module runs the flow once per client and needs a
    second offer.
  - A URN `vct` keeps the suite from fetching SD-JWT VC type metadata over HTTPS.
  - Expected Inji findings, measured with a probe on 2026-10-04: Certify never binds its access tokens
    (`token_type: Bearer`, no `cnf`), so with `sender_constrain=dpop` every credential request fails with
    `invalid_dpop_proof` "Access token is not DPoP-bound: cnf claim is missing"; SD-JWT credentials carry
    `cnf.kid` (a `did:jwk`) instead of `cnf.jwk` (suite condition `VCIEnsureSdJwtCnfMatchesProofKey`); the token
    endpoint does not authenticate clients. No mTLS code was found in Certify, so the mTLS variant may fail too.
  - The TLS proxy asks for a client certificate without checking it (`ssl_verify_client optional_no_ca`); the
    suite's mTLS client certificate is `suite-mtls-client.crt` / `.key` from `pki-init`.
  - The runner image copies `conformance/`, so rebuild it (`bash scripts/dc.sh --profile tools build runner`)
    after changing a plan template.
  - Inji Certify needs about 2 minutes to become healthy. Its keystore volume, its database volume and the
    passwords in `$HARNESS_RUN_DIR/env.local` belong together: delete all three or none.
  - The compose properties `mosip.certify.pre-auth-code.*-expiry-seconds` are ignored, because the code reads
    `mosip.certify.pre-auth.*`. The handoff sends `expires_in` per offer instead.
  - How to continue on your own computer:

    ```bash
    git fetch origin
    git switch feat/issuer-path
    bash scripts/check.sh runner    # PASS before you change anything
    ```

### WP-09 runner: Results, benchmark gate, checked REVIEW evidence. TODO

- **Goal**
  - Parse the suite's export zips into full `results.json` v1: result, failing and warning conditions with message,
    block and requirement ids, live suite log URL, and a link to the extracted HTML export. `run-test-plan.py
    --export-dir` saves only the JSON export, so call `conformance.py` `exporthtml` after it finishes.
  - Classify every module against `conformance/benchmark/{certify,verify}.expected-{failures,skips}.json` with the
    table below; `inji-conformance gate --run DIR [--benchmark-dir DIR] [--allow-stale] [--junit FILE]` with the
    exit codes in [runner/README.md](../runner/README.md); JUnit XML for CI.
  - Remove the temporary `browser` block from `conformance/plans/verify.oid4vp-1final-verifier.json`. On the
    screenshot WAITING state the responder reads `GET /v1/verify/vp-result/{transactionId}` from Inji Verify,
    renders it to a PNG (`pillow`), uploads it with `POST /api/log/{id}/images/{placeholder}`, and records the
    checked verdict (happy flow `valid`, negative modules `invalid`, from the template's `review` block).
  - Seed the benchmark from the WP-06 and WP-08 runs. Every entry has `comment` (the reason), `owner` (`inji`,
    `suite` or `environment`), `spec` (clause), `issue` (path of the finding draft) and a wildcard
    `configuration-filename` such as `*certify.oid4vci-1_0-issuer*.json` (matched with `fnmatch` against the
    rendered config path).
  - Cross-check: fail loudly when the gate, computed without the two harness extensions (REVIEW evidence checks and
    `--allow-stale`), disagrees with `run-test-plan.py`'s own exit code for the same benchmark files.
- **Depends on**: WP-06 (DONE), WP-08 (PARTIAL).
- **Owns**: `runner/src/inji_conformance/` except `report/`, `runner/tests/` except `report/`,
  `conformance/benchmark/`, `conformance/plans/`.
- **Acceptance check**
  - `bash scripts/check.sh runner` prints PASS, with parser, classifier and gate tests on recorded fixtures.
  - Two live runs exit 0 and print `gate: 0 regressions, <n> known gaps, 0 stale`: the WP-08 command block
    without `--no-gate`, and the same block for Inji Verify (`--profile verify`, and only
    `inji-conformance run --component verify --out /reports/wp09-verify` inside the runner container).
  - With one benchmark entry deleted,
    `bash scripts/dc.sh run --rm runner inji-conformance gate --run /reports/<run>/certify` exits 1 and names
    the module and condition.
  - No module ends with result REVIEW without an evidence image.
- **Notes**
  - Verdict table (the runner computes `verdict` once; the report, the gate and the Java bridge only read it):

    | Suite outcome | Benchmark | Verdict | Gate |
    |---|---|---|---|
    | PASSED | not listed | `conforms` | ok |
    | PASSED, or a listed condition did not occur | listed | `stale_benchmark` | fails; warns with `--allow-stale` |
    | WARNING or FAILED | every condition listed | `known_gap` | ok |
    | WARNING or FAILED | any condition not listed | `regression` | fails |
    | REVIEW | checked verdict matches, evidence uploaded | `conforms` | ok |
    | REVIEW | verdict differs or no evidence | `regression` | fails |
    | SKIPPED | listed in expected skips | `not_applicable` | ok |
    | SKIPPED | not listed | `regression` | fails |
    | INTERRUPTED or timeout | any | `regression` ("handoff not delivered" or "timeout") | fails |

  - The benchmark file format is the suite's own expected-failures format (`test-name`, `variant`,
    `configuration-filename`, `current-block`, `condition`, `expected-result`, `comment`) plus `owner`, `spec` and
    `issue`. The suite's loader ignores extra keys, so the same file also works for
    `run-test-plan.py --expected-failures-file`. Schema: `conformance/schema/benchmark.schema.json`; examples in
    `conformance/schema/examples/`.
  - Never blame Inji for a suite limitation: such entries get owner `suite`.
  - The suite's exports contain the private keys of the suite configuration: never commit them.

### WP-10 platform: One-command scripts. TODO

- **Goal**
  - `run-conformance.sh` (created by this task) with `--component certify|verify`, `--combined`, `--runner-only`,
    `--modules`, `--track`, `--serial`, `--allow-stale`, `--keep-stack`, `--out`, `--help` with examples. Runner
    flags pass through unchanged, so WP-14 needs no edit here. `HARNESS_COMPOSE_FILES` adds Compose override
    files (used by the demo regression in WP-17 and WP-18).
  - Default mode runs each component through its testrig (`testrigs/run-testrig.sh`, when it exists) and also
    starts the `reports` profile, so the stock S3 upload to MinIO runs. `--runner-only` skips testrig and MinIO.
  - `run-full-stack-conformance.sh` (created by this task): `--prepare-only` (pull images, build the runner and
    testrig images) and `--no-prepare`; preflight (Docker, Compose v2, free ports, memory); `env.local`
    through `scripts/dc.sh`; `up --wait`; seed; run; testrig step; consolidated report through
    `inji-conformance report`; teardown in a `trap`; exit code = the gate's.
  - Logs and a run manifest (git commit, image digests, times; `conformance/schema/run-manifest.schema.json`) in
    `$HARNESS_RUN_DIR/reports/<run id>/`. A rerun starts from a clean stack and gives the same verdicts.
- **Depends on**: WP-09 (TODO), WP-13 (DONE).
- **Owns**: `run-conformance.sh`, `run-full-stack-conformance.sh`, `scripts/lib/`, and `scripts/dc.sh` for the
  `down` fix in [open problems](#open-problems-found-by-finished-tasks).
- **Acceptance check**

  ```bash
  ./run-conformance.sh --component verify --runner-only     # exit 0, prints the report folder
  ./run-conformance.sh --component certify --runner-only    # exit 0, prints the report folder
  ./run-full-stack-conformance.sh --prepare-only
  ./run-full-stack-conformance.sh --no-prepare --runner-only   # exit 0, results for both components
  bash scripts/check.sh shell                               # PASS
  docker ps -q --filter label=com.docker.compose.project=ps01-harness   # prints nothing
  ```

  Two consecutive combined runs give exit 0 from
  `bash scripts/dc.sh run --rm runner inji-conformance diff /reports/<run 1> /reports/<run 2>`.
- **Notes**
  - Can start now: argument parsing, `--help`, preflight and `--prepare-only` do not need WP-09.
  - Ports to check in preflight: 18443, 18444 (suite), 18450, 18451 (TLS proxy), 18460, 18461 (Certify and Verify
    debug ports), 18900, 18901 (MinIO). Error messages say what to do, for example which variable moves a port.
  - `up --wait` fails when a one-shot container that nothing depends on has exited (Compose 5.5.1, measured), which
    is why `pki-init` is only in the `verify`, `certify` and `tools` profiles and MinIO's bucket is created by a
    `post_start` hook.
  - Pull and build before starting the stack; the first pull is about 2 GB compressed.
  - Git Bash rewrites paths given to `docker`; `scripts/dc.sh` already sets `MSYS_NO_PATHCONV=1` and passes native
    paths, so call Compose only through it.

### WP-12 testrig: Inji Certify rig, MinIO upload, testrig image. TODO

- **Goal**
  - Inji Certify rig: `OpenIDConformanceTest`, the two conformance suite XML files and `ConformanceRigRunner`, in
    the same shape as the Inji Verify rig (WP-11). The Certify runner must skip the Keycloak user creation, OTP
    setup and database cleanup that the stock `InjiTestRunner.main` runs before any test.
  - `testrigs/build.sh` (created by this task): host Maven when JDK 21 and Maven exist, else the
    `maven:3.9-eclipse-temurin-21` image with a cache volume.
  - `testrigs/Dockerfile` (created by this task): Temurin 21 JRE, Python 3, the runner package, both shaded jars,
    the suite XML files.
  - `testrigs/run-testrig.sh <certify|verify> [--results FILE | --invoke]` (created by this task): `docker run` on
    the `ps01-harness` network with S3 settings only from the environment: `s3-host=http://minio:9000`,
    `s3-account=automationtests`, `s3-region=us-east-1`, `push-reports-to-s3=yes`, user `MINIO_ROOT_USER`
    (default `harness`) and `MINIO_ROOT_PASSWORD` from `$HARNESS_RUN_DIR/env.local`; copies the report into the
    run folder.
  - `testrigs/upstream-patches/<rig>/`: `git format-patch --relative` series of the team's commits per rig.
- **Depends on**: WP-09 (TODO), WP-11 (DONE).
- **Owns**: `testrigs/`.
- **Acceptance check**

  ```bash
  bash testrigs/build.sh                       # both shaded jars
  docker build -f testrigs/Dockerfile .        # the testrig image (tag as the task decides)
  bash scripts/dc.sh --profile certify --profile reports up -d --wait
  bash testrigs/run-testrig.sh certify --invoke; rc=$?
  bash scripts/dc.sh run --rm minio-mc ls local/automationtests/injicertify/
  bash scripts/dc.sh --profile '*' down -v; echo "exit $rc"
  ```

  Expected: the exit code equals the gate's (0 with the current benchmark), and the listing shows
  `mosip-ps01-injicertify-*-report_T-*_P-*_S-*_F-*.html`. The same with `verify` and `injiverify`.
  `git apply --check --directory=api-test` succeeds for each patch series on a clean checkout of the upstream
  commit (`203b143` for Certify, `6a6ab3b` for Verify). `git status --porcelain -- testrigs` prints nothing after
  the commit.
- **Notes**
  - Can start now: the Certify rig integration in consume mode
    (`-Dconformance.results.file=../../conformance/schema/examples/results-certify.example.json`), `build.sh` and
    the Dockerfile do not need WP-09.
  - Reuse `RigRun` and `TestNgResults` from the bridge. The runner must write `<out>/<component>/results.json`.
  - The Certify rig uses apitest-commons 1.6.0 (Verify uses 1.5.0); 1.6.0 also reads the `TestCaseName`
    attribute. The bridge keeps apitest-commons in `provided` scope, so each rig keeps its own version.
  - `EmailableReport` leaves out any suite whose name contains "Master Suite", so rows must sit in the child suite.
    A known-issue skip message must contain the whole `GlobalConstants.KNOWN_ISSUES` text, or it is also counted
    as a plain skip.
  - The stock `InjiTestRunner` runs every file in `testNgXmlFiles/` whose name contains `mastertestsuite`, so the
    conformance suite file joins every normal rig run; with no `conformance.*` setting it must give one Ignored row.
  - Measured cold build of the Certify rig alone: 14 min 59 s, mostly downloads (the rig pom declares a snapshots
    repository that Maven probes for every artifact). Shaded jars are about 405-413 MB. Each rig run takes 5-7
    minutes, nearly all of it the stock resource extraction from the jar.
  - TestNG's output folder is set relative to the working directory, so `conformance.report.dir` must be on the
    same drive as the working directory on Windows.
  - Surefire is limited to `junit-jupiter` in the bridge, because apitest-commons brings the Vintage engine and
    JUnit 4.10.
  - `*.inji.test` names exist only inside the Compose network, so invoke mode must run the rig in a container.
  - Runtime output (`testng-report/`, extracted resources) must go to `$HARNESS_RUN_DIR`, never into `testrigs/`.

### WP-14 runner: Parallel execution and HAIP readiness track. TODO

- **Goal**
  - `--combined` runs the issuer and verifier plans at the same time (one `run-test-plan.py` per plan, distinct
    aliases, one responder). `--serial` keeps the old order for comparison. Modules inside a plan stay serial,
    because a configuration with an `alias` makes `run-test-plan.py` run one module at a time.
  - `--track haip` runs `oid4vci-1_0-issuer-haip-test-plan` and `oid4vp-1final-verifier-haip-test-plan` with the
    best request or offer Inji can produce. Results carry `gating: false` and never change the exit code.
  - The run manifest records wall time per plan.
- **Depends on**: WP-10 (TODO).
- **Owns**: `runner/src/inji_conformance/` except `report/`, `runner/tests/` except `report/`,
  `conformance/plans/`.
- **Acceptance check**

  ```bash
  ./run-conformance.sh --combined --runner-only               # exit 0
  ./run-conformance.sh --combined --runner-only --serial      # exit 0
  ./run-conformance.sh --combined --runner-only --track haip  # exit 0, results hold failures with gating: false
  ```

  `inji-conformance diff <serial run> <parallel run>` exits 0, and both manifests carry wall times.
- **Notes**
  - The pre-authorized code grant is not allowed with `fapi_profile=vci_haip`, and Inji Verify has no
    `direct_post.jwt` and no `x509_hash`, so both HAIP plans are expected to fail; that is the point of a
    readiness track.
  - Decided not to build: splitting one plan across several suite plans (`--shards`), and a certification-package
    command (the suite refuses a package for any plan with failures or without a certification profile, which is
    every Inji 1.0 plan today).

### WP-15 platform: GitHub Actions workflow. TODO

- **Goal**: `.github/workflows/full-stack-conformance.yml` (created by this task) with
  - triggers: push, pull request, release published, weekly schedule, `workflow_dispatch` (inputs component,
    track, strict, image overrides) and `workflow_call` (so Inji release pipelines can call it with new image
    digests);
  - concurrency per ref with cancel-in-progress;
  - jobs `checks` (`bash scripts/check.sh all`), `conformance` (matrix certify, verify; per-module mode with the
    testrig), `combined` (merged report, badge, diff against the last successful `main` run's artifact),
    `full-stack` (release, schedule and dispatch only);
  - image cache with `docker save` / `docker load`, keyed by a hash of
    `bash scripts/dc.sh --profile '*' config --images`; Maven and pip caches;
  - artifacts uploaded with `if: always()`; `summary.md` from the report into `GITHUB_STEP_SUMMARY`;
  - the job fails when either component regresses;
  - `.github/examples/inji-release-caller.yml`: the short workflow an Inji repository adds so its release run calls
    this one with new image digests;
  - `scripts/ci-local.sh <component>` runs the same steps on a developer machine.
- **Depends on**: WP-10, WP-12 (TODO), WP-13 (DONE).
- **Owns**: `.github/`, `scripts/ci-local.sh`.
- **Acceptance check**

  ```bash
  actionlint .github/workflows/full-stack-conformance.yml .github/examples/inji-release-caller.yml   # no output, exit 0
  bash scripts/ci-local.sh verify             # exit 0, writes the same artifact layout the workflow uploads
  ./run-conformance.sh --component certify    # per-module mode: exit 0, prints the testrig report path and its MinIO key
  ```

  Then one real run on GitHub; its URL goes into `docs/test-report.md`.
- **Notes**
  - The GitHub repository exists, so a real run is possible as soon as the workflow lands.
  - `CI=true` (set by GitHub Actions) makes `scripts/check.sh` strict: a missing tool fails instead of skipping.
  - GitHub's documentation gives hosted Linux runners 4 vCPU and 16 GB for public repositories and 2 vCPU and
    7 GB for private ones; not measured by the team yet. Peak memory of the Certify stack was 1.5 GiB.
  - Can start now with `actionlint` only; the jobs need WP-10 and WP-12 to run.

### WP-16 delivery: Documentation set. TODO

- **Goal**: documents a newcomer can follow without help, written against the shipped scripts (WP-10) and the
  bridge (WP-11):
  - `docs/README.md` (step-by-step install and run on Windows, Linux and macOS; prerequisites; expected output);
  - `docs/architecture.md` (components, network, sequence and user-flow diagrams as Mermaid plus SVG, the design
    decisions);
  - `docs/api-automation.md` (every suite REST call and Inji API used, with examples; how `run-test-plan.py` is
    reused);
  - `docs/handoffs.md` (per component: what the suite waits for, how the harness answers, evidence, limits);
  - `docs/testrig-integration.md`, `docs/benchmark.md`, `docs/self-certification.md`, `docs/troubleshooting.md`,
    `docs/ci.md`, `docs/configuration.md`, `docs/reference/cli.md`, `docs/reference/results-schema.md`;
  - `docs/tools/check_docs.py`, run by `bash scripts/check.sh docs`: markdownlint, every relative link and image
    resolves, every command block carries the date it was last run (one agreed marker, for example
    `<!-- run 2026-10-08 -->`).
- **Depends on**: WP-10 (TODO), WP-11 (DONE).
- **Owns**: `docs/` except the files WP-17 and WP-18 own, including `docs/tools/` and `docs/diagrams/`.
- **Acceptance check**: `bash scripts/check.sh docs` exits 0; removing one dated marker or breaking one link
  makes it exit 1.
- **Notes**
  - Can start now: `docs/tools/check_docs.py` and the documents about finished parts (compose, bridge, report).
  - Much of the material exists in the lane READMEs (`compose/`, `runner/`, `conformance/`, `testrigs/`,
    `third_party/`); link to them rather than copy.
  - `docs/ci.md` and the Certify part of `docs/testrig-integration.md` get their final pass in WP-18.
  - Decide how the checker treats this file and `CONTRIBUTING.md`, which hold commands for future tasks.

### WP-17 delivery: Test report, test data and Inji findings. TODO

- **Goal**
  - `docs/test-report.md`: unit test counts per language; every integration and end-to-end run with date, commit,
    duration and peak memory (`docker stats`); the robustness cases below; one row per fresh-clone run and newcomer
    walkthrough (OS, Docker version, duration, outcome).
  - `demo/regression.compose.yml`: a Compose override that makes the gate fail by configuration only.
  - Build comparison (drop first if late): one run with `CERTIFY_IMAGE=injistack/inji-certify-with-plugins:1.0.0-alpha.1`,
    diffed against the default image run.
  - `docs/test-cases.md` (id, purpose, steps, expected, actual, date), `docs/test-data.md` (credential
    configuration, offer claims, DCQL query, every generated key and password and where it lives, suite
    configuration fields).
  - `docs/findings/*.md`: one issue draft per Inji gap a run confirmed (benchmark owner `inji`). Suite-side
    limitations (owner `suite`) are listed separately, never as Inji findings.
  - `docs/certification-readiness.md`: HAIP gaps ranked by effort, from the HAIP track.
  - `docs/evidence/<date>-<run id>/`: `summary.html`, `results.json`, `badge.svg`, manifest.
- **Depends on**: WP-09, WP-12, WP-14, WP-16 (all TODO).
- **Owns**: `docs/test-report.md`, `docs/test-cases.md`, `docs/test-data.md`, `docs/findings/`,
  `docs/certification-readiness.md`, `docs/evidence/`, the evidence rule in `docs/tools/`,
  `demo/regression.compose.yml`.
- **Acceptance check**
  - `bash scripts/check.sh docs` passes, including a rule that every run cited in `docs/test-report.md` has a
    folder in `docs/evidence/` with a manifest dated 2026-10-04 or later.
  - `bash scripts/check.sh secrets` finds no key material under `docs/`.
  - Every finding has the headings Summary, Affected version, Spec reference, Suite condition, Steps, Expected,
    Actual, Evidence, Proposed fix.
  - `HARNESS_COMPOSE_FILES=demo/regression.compose.yml ./run-conformance.sh --component <c> --runner-only` exits 1
    and names the affected module.
- **Notes**
  - Robustness cases: R1 two runs, `diff` exit 0; R2 Inji Verify stopped mid-run, the module fails as "handoff not
    delivered" and the stack is torn down; R3 suite restarted mid-run (`run-test-plan.py` retries,
    `CONFORMANCE_RESTART_RETRIES`, or fails clearly); R4 the configuration regression above; R5 parallel and serial
    give the same verdicts; R6 a used port stops preflight with the fix in the message.
  - Never commit raw suite exports: they hold the private keys of the suite configuration.
  - Candidate findings already measured: the DPoP binding, `cnf.kid` and client-authentication gaps in the WP-08
    notes; the Verify items in [open problems](#open-problems-found-by-finished-tasks).

### WP-18 delivery: Demo script, video and deck material, final README. TODO

- **Goal**
  - `demo/demo.sh`: preflight, full run, report paths; `--regression` reruns with
    `HARNESS_COMPOSE_FILES=demo/regression.compose.yml`, shows the failing gate and the diff, then restores.
  - Final pass of every document against the shipped code, completing `docs/ci.md` and the Certify and image parts
    of `docs/testrig-integration.md`.
  - `docs/demo/video-storyboard.md` (shots, timings, narration, under 5 minutes) and `docs/demo/deck-outline.md`.
  - Final `README.md`: badge from a recorded run with its date, one-command quick start, what you get, docs index,
    licences and imported code.
  - `docs/submission-checklist.md`: every required artefact, where it lives, owner, status.
- **Depends on**: WP-13 (DONE), WP-15, WP-16, WP-17 (TODO).
- **Owns**: `demo/` except `regression.compose.yml`, `docs/demo/`, `README.md`, `docs/submission-checklist.md`.
- **Acceptance check**

  ```bash
  rm -rf ../fresh-clone
  git -c core.longpaths=true clone https://github.com/Paradox-73/Automated_Conformance_Testing_for_Inji_Certify_and_Inji_Verify.git ../fresh-clone
  cd ../fresh-clone && git config core.longpaths true
  ./run-full-stack-conformance.sh --prepare-only
  ./run-full-stack-conformance.sh --no-prepare
  ```

  Expected: exit 0 and the paths of `summary.html`, `badge.svg`, both testrig reports and the MinIO object keys.
  `bash demo/demo.sh --regression` exits 0 after showing a gate exit code of 1 that names the injected regression
  and a diff listing only the affected modules. Every README command was run on the fresh clone on the date
  written next to it.
- **Notes**
  - First regression candidate, Certify `mosip.certify.allow-c-nonce=false` (removes `nonce_endpoint`), may change
    no verdict: the nonce endpoint is optional in OpenID4VCI 1.0, and with DPoP every credential request already
    fails earlier. Fallback: a change that breaks a metadata check, for example a `credential_issuer` that no longer
    matches the issuer URL.

## How to split the remaining work

| Lane | Owns (only this lane edits these) | Remaining tasks, in order | Can start today |
|---|---|---|---|
| platform | `docker-compose.yml`, `compose/`, `scripts/`, root scripts, `.github/`, `.gitignore`, `.gitattributes`, `.gitguardian.yaml`, `.editorconfig` | open problems (Verify `init.sql`, `dc.sh down`), WP-10, WP-15 | yes: the two open problems, then the WP-10 skeleton and preflight |
| runner | `runner/` except `runner/src/inji_conformance/report/` and `runner/tests/report/`; `conformance/`; `third_party/` | WP-08, WP-09, WP-14 | yes: finish WP-08 from the branch |
| testrig | `testrigs/` | WP-12 | yes: Certify rig in consume mode, `build.sh`, `Dockerfile` |
| delivery | `docs/`, `demo/`, `README.md`, `CONTRIBUTING.md`, `runner/src/inji_conformance/report/`, `runner/tests/report/` | WP-16, WP-17, WP-18 | yes: `docs/tools/check_docs.py` and docs of finished parts |

- One person per lane at a time. With two people: one takes runner (the longest chain), the other takes platform
  and testrig, which share no folder; delivery goes to whoever is free first.
- Fixed seams, so no lane edits another lane's file: `runner/src/inji_conformance/cli.py` (runner) already
  registers `report` and `diff`, which live in the report package (delivery); `runner/pyproject.toml` (runner)
  declares the report's dependencies; `bash scripts/check.sh docs` (platform) runs `docs/tools/check_docs.py`
  (delivery); `run-conformance.sh` (platform) passes runner flags through unchanged.
- If a task truly needs a change in another lane's folder, ask that lane's owner to make it in their own pull
  request.
- This file belongs to delivery for its structure, but every pull request that finishes or advances a task edits
  that task's row and card here. Edit only your own task's row to avoid merge conflicts.

## Definition of done

A task is DONE only when all of these hold, in one pull request:

1. The tests pass: `bash scripts/check.sh all` prints no FAIL (and the lane's own test command, for example `mvn`
   for testrigs).
2. The task's acceptance check above was run on the date written in the pull request, with its output pasted into
   the pull request description.
3. The docs that describe the changed parts are updated (the lane README, and `docs/` once WP-16 exists). They
   state only what was run, with the date.
4. This file is updated in the same pull request: status set to DONE with the commit ids, the card replaced by
   "done" notes (what was measured, what is left for later tasks).
5. A teammate reviewed and approved the pull request.
6. `git status --porcelain` is empty after the run: no runtime output was written into the repository.
