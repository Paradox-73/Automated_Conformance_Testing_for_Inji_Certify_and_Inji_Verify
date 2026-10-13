### Inji conformance: gate passed

Run `20261013T222630Z-e4420c`

| Component | Modules | Conforms | Known gap | Regression | Not applicable | Stale benchmark |
|---|---:|---:|---:|---:|---:|---:|
| certify | 15 | 0 | 0 | 15 | 0 | 0 |

Regressions:

- certify `oid4vci-1_0-issuer-metadata-test`: result FAILED: CheckForUnexpectedParametersInCredentialIssuerMetadata, CheckForUnexpectedParametersInServerMetadata, VCICredentialIssuerMetadataValidation, VCIValidateFormatOfCredentialConfigurationsInMetadata
- certify `oid4vci-1_0-issuer-metadata-test-signed`: result FAILED: EnsureContentTypeApplicationJwt, VCIDecodeSignedCredentialIssuerMetadata
- certify `oid4vci-1_0-issuer-happy-flow`: result FAILED: CheckServerConfiguration
- certify `oid4vci-1_0-issuer-happy-flow-additional-requests`: result FAILED: CheckServerConfiguration
- certify `oid4vci-1_0-issuer-happy-flow-multiple-clients`: result FAILED: CheckServerConfiguration
- certify `oid4vci-1_0-issuer-happy-flow-skip-notification`: result FAILED: CheckServerConfiguration
- certify `oid4vci-1_0-issuer-batch-issuance`: result FAILED: CheckServerConfiguration
- certify `oid4vci-1_0-issuer-fail-invalid-nonce`: result FAILED: CheckServerConfiguration
- certify `oid4vci-1_0-issuer-fail-invalid-jwt-proof-signature`: result FAILED: CheckServerConfiguration
- certify `oid4vci-1_0-issuer-fail-invalid-key-attestation-signature`: result FAILED: CheckServerConfiguration
- certify `oid4vci-1_0-issuer-fail-missing-proof`: result FAILED: CheckServerConfiguration
- certify `oid4vci-1_0-issuer-fail-unsupported-encryption-algorithm`: result FAILED: CheckServerConfiguration
- certify `oid4vci-1_0-issuer-fail-unknown-credential-configuration`: result FAILED: CheckServerConfiguration
- certify `oid4vci-1_0-issuer-fail-unknown-credential-identifier`: result FAILED: CheckServerConfiguration
- certify `oid4vci-1_0-issuer-fail-on-access-token-in-query`: result FAILED: CheckServerConfiguration
