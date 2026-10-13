# Inji Certify rejects key proofs that name the client in iss

## Summary

In four issuer modules the suite authenticates at the token endpoint (`private_key_jwt`) and therefore puts its
`client_id` into the `iss` claim of the key proof, as OpenID4VCI 1.0 Appendix F.1 asks for a client that is
not anonymous. Inji Certify rejects every proof that has an `iss` claim: its log says "JWT iss claim has value
inji-conformance-wallet, must be" (empty), and it answers HTTP 400 `invalid_proof`. Certify does not
authenticate clients at its token endpoint, so it treats every pre-authorized client as anonymous and requires
proofs without `iss`; a wallet that authenticates cannot get a credential.

## Affected version

`injistackqa/inji-certify-with-plugins:develop@sha256:b5022884fb308fe8f697d11a2f6256714a97cec3188dbc5ed8b9aa59d1cacf5c` (Inji Certify 1.0 line, `certify-service` `1.0.0-beta.1-SNAPSHOT`), configured as in `compose/certify/`.

## Spec reference

OpenID4VCI 1.0, the `jwt` proof type (claim `iss`, Appendix F.1) and client authentication at the token
endpoint; the suite logs `OID4VCI-1FINAL-8.3` for the failing status check.

## Suite condition

`EnsureHttpStatusCodeIsAnyOf` in block "Verify Credential Endpoint Response" of
`oid4vci-1_0-issuer-happy-flow-additional-requests`, `-happy-flow-multiple-clients`,
`-happy-flow-skip-notification` and `oid4vci-1_0-issuer-fail-on-access-token-in-query`.

## Steps

1. `./run-conformance.sh --component certify --runner-only`.
2. The suite redeems the offer with client authentication and sends a credential request whose JWT proof has
   `iss` = `inji-conformance-wallet`.

## Expected

The credential (HTTP 200), or, if Certify does not support client authentication, the token request refused, so
that the wallet does not send a proof it will reject.

## Actual

```text
HTTP 400 {"error":"invalid_proof","error_description":"None of the submitted proofs passed validation."}
Certify log: com.nimbusds.jwt.proc.BadJWTException: JWT iss claim has value inji-conformance-wallet, must be
```

## Evidence

The four modules above in [`docs/evidence/2026-10-13-20261013T222910Z-f08c5b/`](../evidence/2026-10-13-20261013T222910Z-f08c5b/); Certify's container log (`logs/compose.log` of the run folder, not committed:
it holds run-time data). First measured 2026-10-14.

## Proposed fix

Authenticate clients at the token endpoint when they present credentials (`private_key_jwt`, client
attestation), remember on the access token whether the client was authenticated, and accept `iss` equal to that
client's id; keep rejecting `iss` only for anonymous pre-authorized access.
