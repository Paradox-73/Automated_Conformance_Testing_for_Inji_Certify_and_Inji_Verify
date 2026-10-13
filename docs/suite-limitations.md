# Conformance suite limitations

Problems the harness meets that are in the OpenID Foundation conformance suite (release-v5.3.1), not in Inji. Their
benchmark entries have owner `suite`; they are never reported as Inji findings (those are in
[findings/](findings/README.md)).

| Benchmark entry | What happens | Why it is the suite | What would remove it |
|---|---|---|---|
| `VCIValidateFormatOfCredentialConfigurationsInMetadata` (warning), `oid4vci-1_0-issuer-metadata-test` | "Found credential configurations with unsupported formats": the `ldp_vc` configuration `FarmerCredential` | `ldp_vc` is a format of OpenID4VCI 1.0 Appendix A.1; this suite version checks only SD-JWT VC and mdoc configurations | A suite release that knows `ldp_vc`, or a Certify configuration without it |
| `CheckForUnexpectedParametersInServerMetadata` (warning), `oid4vci-1_0-issuer-metadata-test` | `interactive_authorization_endpoint` and `require_interactive_authorization_request` reported as unknown | Both come from a later OpenID4VCI draft (interactive authorization) that this suite version does not know | A suite release that knows them |
| `ValidateRequestObjectSignatureAgainstX5cHeader` (failure), every module of the `x509_san_dns` verifier configuration | "Error verifying JWT signature using x5c leaf certificate" for Inji Verify's EdDSA request objects | The signature verifies with `openssl pkeyutl -verify` against the same `x5c` certificate (measured 2026-10-14) | EdDSA support in the suite's x5c check, or ES256 signing in Inji Verify ([findings/verify-request-signing-eddsa-only.md](findings/verify-request-signing-eddsa-only.md)) |

Two further suite behaviours the harness works around (no benchmark entry needed):

- `run-test-plan.py` stops a whole plan after three modules in a row that did not reach FINISHED. Against Inji
  Certify a failing condition inside a request the suite answers ends a module INTERRUPTED, so the runner raises
  the limit (`CONFORMANCE_MAX_CONSECUTIVE_FAILURES=1000`) and judges such modules on their logged conditions, as
  `run-test-plan.py` does when it analyses results.
- A verifier module that ends in REVIEW waits until someone uploads a screenshot. The harness uploads an image of
  Inji Verify's verdict, read from its API ([handoffs.md](handoffs.md)).
