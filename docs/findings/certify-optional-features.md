# Optional OpenID4VCI features Inji Certify does not offer: batch issuance, key attestation, response encryption

## Summary

The suite skips three issuer modules because Inji Certify's metadata does not offer the feature they test:
`batch_credential_issuance`, key attestations (`key_attestations_required`) and credential response encryption
(`credential_response_encryption`). All three are optional in OpenID4VCI 1.0; HAIP deployments may require key
attestation and encryption. They are expected skips in the benchmark, owner `inji`, so that the gate notices when
Inji adds one of them.

## Affected version

`injistackqa/inji-certify-with-plugins:develop@sha256:b5022884fb308fe8f697d11a2f6256714a97cec3188dbc5ed8b9aa59d1cacf5c` (Inji Certify 1.0 line, `certify-service` `1.0.0-beta.1-SNAPSHOT`), configured as in `compose/certify/`.

## Spec reference

OpenID4VCI 1.0: Credential Issuer Metadata (`batch_credential_issuance`, `credential_response_encryption`) and
key attestations.

## Suite condition

Result SKIPPED for `oid4vci-1_0-issuer-batch-issuance`, `oid4vci-1_0-issuer-fail-invalid-key-attestation-signature`
and `oid4vci-1_0-issuer-fail-unsupported-encryption-algorithm`.

## Steps

1. `./run-conformance.sh --component certify --runner-only`.

## Expected

Either the feature is offered and the module runs, or the module is skipped (today's behaviour, listed as expected).

## Actual

The three modules end FINISHED with result SKIPPED; verdict `not_applicable`.

## Evidence

The three modules in [`docs/evidence/2026-10-13-20261013T222910Z-f08c5b/`](../evidence/2026-10-13-20261013T222910Z-f08c5b/); first measured 2026-10-14.

## Proposed fix

None needed for OpenID4VCI 1.0 conformance. For HAIP readiness see
[../certification-readiness.md](../certification-readiness.md).
