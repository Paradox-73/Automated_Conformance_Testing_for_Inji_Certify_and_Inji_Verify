# Handoffs

A handoff is what lets a suite module continue when it waits for something from outside: an offer, an
authorization request, a transaction code, a screenshot. A person normally does it in the suite's web page; the
runner's responder thread (`runner/src/inji_conformance/handoff.py`) does it instead. It polls
`GET /api/runner/running`, keeps the tests whose alias is this run's (`inji-certify-<run id>`,
`inji-verify-<run id>`), and acts on each WAITING test. Every action is a record in `logs/handoffs.jsonl` and in
the module's `handoffs` in `results.json`, with HTTP status and time.

## Inji Certify (issuer plan)

| The suite waits for | It exposes | The responder | Inji API used |
|---|---|---|---|
| a credential offer | `credential_offer_endpoint` | creates a pre-authorized offer with the plan's claims and a new 6-digit transaction code, then `GET <credential_offer_endpoint>?credential_offer_uri=<uri>` | `POST /v1/certify/pre-authorized-data` |
| the transaction code a person would type | `tx_code_endpoint` | `GET <tx_code_endpoint>?code=<that code>`; the suite then redeems the code and requests the credential inside this call | none (the suite calls Inji) |
| a second offer (`happy-flow-multiple-clients` runs the flow once per client) | `credential_offer_endpoint` again | a new offer, because pre-authorized codes are single-use; at most 6 per module | as above |

Before the plan the runner seeds the credential configuration the plan asks for (`inji-conformance seed certify`,
idempotent; `POST /v1/certify/credential-configurations` with a base64 `vcTemplate`). Evidence: the suite's own log
of each module (the token and credential calls it made) in the HTML export, `exports/html/`.

Limits (measured 2026-10-14): every flow module stops at the credential endpoint, because of the Inji findings
listed in [findings/README.md](findings/README.md); the negative modules `fail-invalid-nonce`,
`fail-invalid-jwt-proof-signature` and `fail-missing-proof` pass. The authorization code flow is not tested:
Inji Certify publishes no `authorization_endpoint`.

## Inji Verify (verifier plan)

| The suite waits for | It exposes | The responder | Inji API used |
|---|---|---|---|
| an authorization request | `authorization_endpoint` | creates a request at Inji Verify and sends `GET <authorization_endpoint>?<query>`, the query built exactly as the Inji Verify SDK builds the `openid4vp://` QR code (`inji_verify.authorization_query`, checked against the SDK in a golden test) | `POST /v1/verify/v2/vp-request` |
| a screenshot of the verifier's result (modules that end in REVIEW) | `browser.uploadsRequired` > 0 | reads Inji Verify's verdict for the request's transaction, draws it as a PNG, keeps it in `verify/evidence/` and uploads it into the placeholder | `GET /v1/verify/vp-result/{transactionId}`, suite `POST /api/log/{id}/images/{placeholder}` |

A REVIEW module is `conforms` only when Inji Verify's verdict is the one the module expects (valid for the
positive modules, invalid for the tampered ones, listed in the template's `review` block) and the image was
uploaded. The image shows the verdict as Inji Verify's API reported it, the transaction id and the module; it is not
a screenshot of a browser, and says so.

Measured 2026-10-14 with the default template: all 11 modules conform; 7 end in REVIEW with Inji Verify's verdict
as expected (4 valid, 3 invalid), 4 pass.

## Every component

| Situation | The responder |
|---|---|
| A test stays CONFIGURED for 5 s | starts it (`POST /api/runner/{id}`); the suite starts almost every test by itself |
| Front-channel URLs nobody visited | requests each and marks it visited |
| A poll fails (suite restarting) | records the error in `results.json` `notes` and keeps polling; robustness case R3 survived a suite restart this way |

## When a handoff cannot be delivered

The suite eventually stops waiting, or the run reaches `--timeout-minutes`; such modules end WAITING,
INTERRUPTED without a logged failure, or NOT_STARTED and are regressions with the reason "handoff not delivered or
timeout" or "the module never started". Robustness case R2 (Inji Verify stopped mid-run) shows it:
[test-report.md](test-report.md).
