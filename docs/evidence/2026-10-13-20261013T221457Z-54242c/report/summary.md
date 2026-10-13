### Inji conformance: gate failed

Run `20261013T221457Z-54242c`

| Component | Modules | Conforms | Known gap | Regression | Not applicable | Stale benchmark |
|---|---:|---:|---:|---:|---:|---:|
| verify | 11 | 0 | 0 | 11 | 0 | 0 |

Regressions:

- verify `oid4vp-1final-verifier-happy-flow`: result REVIEW: Inji Verify's verdict was missing, and no evidence image of it was uploaded, so the review is not confirmed
- verify `oid4vp-1final-verifier-minimal-cnf-jwk`: the module ended in status INTERRUPTED: handoff not delivered or timeout
- verify `oid4vp-1final-verifier-request-uri-method-post`: the module ended in status WAITING: handoff not delivered or timeout
- verify `oid4vp-1final-verifier-request-uri-fetched-twice`: the module never started
- verify `oid4vp-1final-verifier-invalid-kb-jwt-signature`: the module never started
- verify `oid4vp-1final-verifier-invalid-credential-signature`: the module never started
- verify `oid4vp-1final-verifier-invalid-sd-hash`: the module never started
- verify `oid4vp-1final-verifier-invalid-kb-jwt-nonce`: the module never started
- verify `oid4vp-1final-verifier-invalid-kb-jwt-aud`: the module never started
- verify `oid4vp-1final-verifier-kb-jwt-iat-in-past`: the module never started
- verify `oid4vp-1final-verifier-kb-jwt-iat-in-future`: the module never started
