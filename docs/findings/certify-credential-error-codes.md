# Inji Certify answers unknown configurations and identifiers with non-standard error codes

## Summary

Two negative issuer modules check the error code of the credential error response. For an unknown
`credential_configuration_id` Inji Certify answers `invalid_credential_request` instead of
`unknown_credential_configuration`. A request with `credential_identifier` is refused as an unknown field
(`invalid_request`, "Unrecognized field 'credential_identifier'"), instead of `unknown_credential_identifier`
for an identifier it never issued.

## Affected version

`injistackqa/inji-certify-with-plugins:develop@sha256:b5022884fb308fe8f697d11a2f6256714a97cec3188dbc5ed8b9aa59d1cacf5c` (Inji Certify 1.0 line, `certify-service` `1.0.0-beta.1-SNAPSHOT`), configured as in `compose/certify/`.

## Spec reference

OpenID4VCI 1.0, Credential Error Response (error codes `unknown_credential_configuration` and
`unknown_credential_identifier`); the suite logs `OID4VCI-1FINAL-8.3.1`.

## Suite condition

`VCIValidateCredentialErrorResponse` in block "Verify Credential Endpoint Response" of
`oid4vci-1_0-issuer-fail-unknown-credential-configuration` ("Expected error code not found in credential error
response: unknown_credential_configuration") and `oid4vci-1_0-issuer-fail-unknown-credential-identifier`
("Non-standard credential error response error code found: invalid_request").

## Steps

1. `./run-conformance.sh --component certify --runner-only`.
2. The suite redeems an offer, then asks for a configuration that does not exist, and in the other module for a
   `credential_identifier` that was never issued.

## Expected

HTTP 400 with `"error": "unknown_credential_configuration"` and `"error": "unknown_credential_identifier"`.

## Actual

```text
HTTP 400 {"error":"invalid_credential_request","error_description":"No credential configuration found for credential_configuration_id"}
HTTP 400 {"error":"invalid_request","error_description":"Unrecognized field 'credential_identifier' in request"}
```

## Evidence

Both modules in [`docs/evidence/2026-10-13-20261013T222910Z-f08c5b/`](../evidence/2026-10-13-20261013T222910Z-f08c5b/); first measured 2026-10-14.

## Proposed fix

Map "no credential configuration found" to `unknown_credential_configuration`. Accept `credential_identifier`
(OpenID4VCI 1.0 credential requests use either it or `credential_configuration_id`) and answer an identifier that
is not in the token's authorization details with `unknown_credential_identifier`.
