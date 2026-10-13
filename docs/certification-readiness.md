# HAIP certification readiness

What stands between Inji and a passing run of the certification-profile plans: the OpenID4VC High Assurance
Interoperability Profile (HAIP) plans of the conformance suite. Measured with the readiness track on 2026-10-14
(run `20261013T222452Z-1865df`, [evidence](evidence/2026-10-13-20261013T222452Z-1865df/)):

<!-- run 2026-10-14 -->
```bash
./run-conformance.sh --combined --runner-only --track haip
```

Results carry `gating: false`: every module is a regression, and the exit code stays 0.

## Inji Verify: `oid4vp-1final-verifier-haip-test-plan` (11 modules)

10 modules stop at the request object, one is skipped (`request_uri_method=post`). Every failing condition is an
Inji Verify gap; the plan sends the request Inji Verify can make today (x509_san_dns, `direct_post`).

| Rank | Gap | Suite conditions | Effort |
|---|---|---|---|
| 1 | `direct_post.jwt` with an encrypted response: `client_metadata` with `jwks` (an encryption key) and `encrypted_response_enc_values_supported`, and decryption of the response | `ValidateResponseMode`, `VP1FinalCheckForKeyIdInClientMetadataJWKs`, `VP1FinalValidateClientMetadataJwksForEncryptedResponse`, `ValidateVpClientMetadataEncryptionForHaip`, `VP1FinalEncryptVPResponse` | large: new response mode and key management |
| 2 | `x509_hash` client id (hash of the leaf certificate) | `ExtractAndValidateX509HashClientId` | small: compute the hash from the signing certificate |
| 3 | ES256 request object signing ([finding](findings/verify-request-signing-eddsa-only.md)) | `ValidateRequestObjectSignatureAgainstX5cHeader` | medium: an EC key type in the keystore and algorithm selection |
| 4 | `request_uri_method=post` ([finding](findings/verify-request-uri-method-post.md)) | module skipped | medium |

## Inji Certify: `oid4vci-1_0-issuer-haip-test-plan` (63 modules)

HAIP allows only the authorization code flow with client attestation and DPoP. Inji Certify offers the
pre-authorized code flow without client authentication, so the plan cannot get far; most modules stop at
configuration the HAIP plan needs before it sends any request:

| First failing condition | Modules | Whose gap |
|---|---|---|
| `CreateClientAttestationJwt`: "Client attestation issuer must not be null or empty" | 39 | the harness's HAIP template has no client attestation issuer key yet; Certify would also need to accept attestation |
| `EnsureCredentialTrustAnchorConfigured` (and the status list trust anchor) | 21 | the template has no trust anchors for Certify's credentials yet |
| metadata modules: `VCICredentialIssuerMetadataValidation`, `EnsureContentTypeApplicationJwt`, `EnsureAuthorizationResponseIssParameterSupportedIsTrue` | 3 | Inji Certify |

Gaps of Inji Certify the HAIP plan names, ranked by effort:

| Rank | Gap | Seen as | Effort |
|---|---|---|---|
| 1 | authorization server metadata: `authorization_endpoint` ([finding](findings/certify-as-metadata-authorization-endpoint.md)), `authorization_response_iss_parameter_supported`, `dpop_signing_alg_values_supported`, `token_endpoint_auth_methods_supported` | `CheckServerConfiguration`, `EnsureAuthorizationResponseIssParameterSupportedIsTrue`, `FAPI2CheckDpopSigningAlgValuesSupported`, `CheckDiscEndpointTokenEndpointAuthMethodsSupportedContainsAttestation` | small, once the features exist |
| 2 | issuer metadata without nulls ([finding](findings/certify-metadata-null-display-values.md)) and signed metadata ([finding](findings/certify-signed-metadata.md)) | `VCICredentialIssuerMetadataValidation`, `EnsureContentTypeApplicationJwt` | small to medium |
| 3 | client authentication at the token endpoint, with `attest_jwt_client_auth` | `CheckDiscEndpointClientAttestationSigningAlgValuesSupported`; [finding](findings/certify-proof-iss-rejected.md) | medium |
| 4 | pushed authorization requests (PAR) and the authorization code flow with DPoP-bound tokens | `CheckDiscEndpointPARSupported` | large |
| 5 | key attestation and credential response encryption ([finding](findings/certify-optional-features.md)) | skipped in the 1.0 plan | large |

## Next steps for the harness

- Give the Certify HAIP template a client attestation issuer key and the credential and status list trust anchors
  (pki-init can make them), so the plan reaches Inji Certify's endpoints in every module.
- Keep both HAIP plans in the weekly CI run (`workflow_dispatch` with `track: haip`), so progress shows as modules
  moving from regression to conforms.
