# Inji Certify rejects a credential request that carries an unknown parameter

## Summary

The suite's issuer happy flow adds a parameter with a random name to the credential request, to check that the
issuer ignores parameters it does not know. Inji Certify answers HTTP 400 `invalid_request` "Unrecognized field
'<name>' in request" and issues nothing. The same strictness makes it reject `credential_identifier` (see
[certify-credential-error-codes.md](certify-credential-error-codes.md)). A wallet that sends any newer or optional
parameter cannot get a credential.

## Affected version

`injistackqa/inji-certify-with-plugins:develop@sha256:b5022884fb308fe8f697d11a2f6256714a97cec3188dbc5ed8b9aa59d1cacf5c` (Inji Certify 1.0 line, `certify-service` `1.0.0-beta.1-SNAPSHOT`), configured as in `compose/certify/`.

## Spec reference

OpenID4VCI 1.0, Credential Request and Credential Response; the suite logs the requirement `OID4VCI-1FINAL-8.3`
for this check. OAuth 2.0 practice, which OpenID4VCI follows, is that unknown request
parameters are ignored.

## Suite condition

`EnsureHttpStatusCodeIsAnyOf` in block "Verify Credential Endpoint Response" of
`oid4vci-1_0-issuer-happy-flow`: "resource endpoint returned an unexpected http status" (expected 200 or 202,
got 400).

## Steps

1. `./run-conformance.sh --component certify --runner-only` (issuer plan, pre-authorized code flow).
2. The harness hands an Inji Certify offer and its transaction code to the suite.
3. The suite redeems the code and sends the credential request with one extra parameter.

## Expected

HTTP 200 with the credential (the unknown parameter is ignored).

## Actual

```text
HTTP 400 {"error":"invalid_request","error_description":"Unrecognized field 'ZUGOIlvQkVvuPk9O' in request"}
```

Certify's log shows a Jackson `HttpMessageNotReadableException` (`Unrecognized field`): the request body is
bound to a class that fails on unknown properties.

## Evidence

Module `oid4vci-1_0-issuer-happy-flow` in [`docs/evidence/2026-10-13-20261013T222910Z-f08c5b/`](../evidence/2026-10-13-20261013T222910Z-f08c5b/) (`certify/results.json`), first measured 2026-10-14.

## Proposed fix

Configure the credential request binding to ignore unknown properties (`@JsonIgnoreProperties(ignoreUnknown =
true)` on the request DTO, or `spring.jackson.deserialization.fail-on-unknown-properties=false` for this
endpoint), and keep explicit validation of the parameters Certify uses.
