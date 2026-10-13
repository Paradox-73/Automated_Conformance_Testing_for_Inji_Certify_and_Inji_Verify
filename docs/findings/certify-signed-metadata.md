# Inji Certify does not offer signed credential issuer metadata

## Summary

Asked for its issuer metadata with `Accept: application/jwt`, Inji Certify answers the unsigned JSON document,
without a content type the suite accepts. Signed metadata is optional in OpenID4VCI 1.0, so this is a missing
optional feature, not a defect; it is listed so that the gate reports it as a known gap and the team can decide
whether to support it (HAIP deployments may expect it).

## Affected version

`injistackqa/inji-certify-with-plugins:develop@sha256:b5022884fb308fe8f697d11a2f6256714a97cec3188dbc5ed8b9aa59d1cacf5c` (Inji Certify 1.0 line, `certify-service` `1.0.0-beta.1-SNAPSHOT`), configured as in `compose/certify/`.

## Spec reference

OpenID4VCI 1.0, signed Credential Issuer Metadata (`application/jwt`); the suite logs `OID4VCI-1FINAL-12.2.2`
and `RFC8414-3.2`.

## Suite condition

`EnsureContentTypeApplicationJwt` and `VCIDecodeSignedCredentialIssuerMetadata` in block "Process Credential
Issuer Metadata Response" of `oid4vci-1_0-issuer-metadata-test-signed` (the module ends INTERRUPTED with result
FAILED).

## Steps

1. `./run-conformance.sh --component certify --runner-only`.
2. The suite requests `/.well-known/openid-credential-issuer` with `Accept: application/jwt`.

## Expected

A JWT (`application/jwt`) holding the metadata, signed by the issuer, when signed metadata is supported.

## Actual

```text
EnsureContentTypeApplicationJwt: Couldn't find content-type header in endpoint_response
VCIDecodeSignedCredentialIssuerMetadata: a string is expected for credential_issuer_metadata_endpoint_response body but JsonNull was found
```

## Evidence

Module `oid4vci-1_0-issuer-metadata-test-signed` in [`docs/evidence/2026-10-13-20261013T222910Z-f08c5b/`](../evidence/2026-10-13-20261013T222910Z-f08c5b/); first measured 2026-10-14.

## Proposed fix

Optional: serve the metadata as a signed JWT for `Accept: application/jwt` with the issuer's signing key, or ask
the suite maintainers to skip this module when the issuer does not advertise signed metadata.
