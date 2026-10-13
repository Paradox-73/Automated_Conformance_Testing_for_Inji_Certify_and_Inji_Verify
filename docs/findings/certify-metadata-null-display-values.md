# Inji Certify writes null for unset display fields in its issuer metadata

## Summary

For a credential configuration created without logo, colours or background image, Inji Certify's issuer
metadata contains `"logo": null`, `"background_color": null`, `"background_image": null` and
`"text_color": null` in `credential_metadata.display`. The metadata schema allows these fields to be left out,
not to be null, so the suite's metadata validation fails, and its parameter check then also reports
`scope`, `cryptographic_binding_methods_supported` and `proof_types_supported` of that configuration as unknown.

## Affected version

`injistackqa/inji-certify-with-plugins:develop@sha256:b5022884fb308fe8f697d11a2f6256714a97cec3188dbc5ed8b9aa59d1cacf5c` (Inji Certify 1.0 line, `certify-service` `1.0.0-beta.1-SNAPSHOT`), configured as in `compose/certify/`, with the credential configuration that `inji-conformance seed certify` creates
(`conformance/plans/certify.oid4vci-1_0-issuer.json`, block `seed`).

## Spec reference

OpenID4VCI 1.0, Credential Issuer Metadata (`credential_configurations_supported`, `display`); the suite logs
`OID4VCI-1FINAL-12.2.3`.

## Suite condition

`VCICredentialIssuerMetadataValidation` (failure) and `CheckForUnexpectedParametersInCredentialIssuerMetadata`
(warning) in block "Process Credential Issuer Metadata Response" of `oid4vci-1_0-issuer-metadata-test`.

## Steps

1. `bash scripts/dc.sh run --rm runner inji-conformance seed certify` on a fresh stack.
2. `GET https://certify.inji.test:18450/.well-known/openid-credential-issuer`.

## Expected

Unset display fields left out of the document.

## Actual

```text
$.credential_configurations_supported.InjiConformanceSdJwtVc.credential_metadata.display[0].logo: null found, object expected
... background_color: null found, string expected; background_image: null found, object expected;
... text_color: null found, string expected
```

## Evidence

Module `oid4vci-1_0-issuer-metadata-test` in [`docs/evidence/2026-10-13-20261013T222910Z-f08c5b/`](../evidence/2026-10-13-20261013T222910Z-f08c5b/); first measured 2026-10-14.

## Proposed fix

Serialise the display objects with `@JsonInclude(JsonInclude.Include.NON_NULL)` (or the global Jackson setting)
so that unset fields are omitted.
