### Inji conformance: gate failed with 1 workaround

Run `20261025T105611Z-5d0671`

- Workaround (certify): The TLS proxy changed Inji Certify's OAuth authorization server metadata: authorization_endpoint added by the TLS proxy. Covers the Inji finding `docs/findings/certify-as-metadata-authorization-endpoint.md`; turn it off with `CERTIFY_AS_METADATA=as-is`.

| Component | Modules | Conforms | Known gap | Regression | Not applicable | Stale benchmark |
|---|---:|---:|---:|---:|---:|---:|
| certify | 15 | 1 | 8 | 3 | 3 | 0 |

Regressions:

- certify `oid4vci-1_0-issuer-fail-invalid-nonce`: result FAILED: not in the benchmark: EnsureHttpStatusCodeIs400, VCIValidateCredentialErrorResponse
- certify `oid4vci-1_0-issuer-fail-invalid-jwt-proof-signature`: result FAILED: not in the benchmark: EnsureHttpStatusCodeIs400, VCIValidateCredentialErrorResponse
- certify `oid4vci-1_0-issuer-fail-unknown-credential-configuration`: result FAILED: not in the benchmark: EnsureHttpStatusCodeIs400

Compared with `20261025T105438Z-68b2e2`: 3 changed, 0 added, 0 removed, 3 new regressions, 0 fixed.
