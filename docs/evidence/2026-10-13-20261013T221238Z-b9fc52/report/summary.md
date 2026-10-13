### Inji conformance: gate failed

Run `20261013T221238Z-b9fc52`

| Component | Modules | Conforms | Known gap | Regression | Not applicable | Stale benchmark |
|---|---:|---:|---:|---:|---:|---:|
| certify | 15 | 1 | 8 | 3 | 3 | 0 |

Regressions:

- certify `oid4vci-1_0-issuer-fail-invalid-nonce`: result FAILED: not in the benchmark: EnsureHttpStatusCodeIs400, VCIValidateCredentialErrorResponse
- certify `oid4vci-1_0-issuer-fail-invalid-jwt-proof-signature`: result FAILED: not in the benchmark: EnsureHttpStatusCodeIs400, VCIValidateCredentialErrorResponse
- certify `oid4vci-1_0-issuer-fail-unknown-credential-configuration`: result FAILED: not in the benchmark: EnsureHttpStatusCodeIs400
