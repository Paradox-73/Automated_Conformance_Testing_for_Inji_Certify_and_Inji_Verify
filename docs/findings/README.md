# Inji findings

Issue drafts for gaps the conformance runs found in Inji Certify and Inji Verify, ready to file with the Inji
teams. Each draft has the same headings (Summary, Affected version, Spec reference, Suite condition, Steps,
Expected, Actual, Evidence, Proposed fix), checked by `bash scripts/check.sh docs`. Every benchmark entry with
owner `inji` names one of these files in its `issue` field. Problems of the conformance suite itself are in
[../suite-limitations.md](../suite-limitations.md).

Known gap patched by the harness: the first finding below is not measured as a known gap in the default run, because
the TLS proxy adds the missing `authorization_endpoint` so the rest of the issuer plan can run. Such a run records
the change in `results.json` (`workarounds`), and its gate reads "passed with 1 workaround". A gate result for Inji
Certify is therefore against patched metadata unless the run used `CERTIFY_AS_METADATA=as-is`
([configuration](../configuration.md#inji-certify-metadata-workaround)).

| Draft | Component | Severity for conformance | Modules |
|---|---|---|---|
| [certify-as-metadata-authorization-endpoint.md](certify-as-metadata-authorization-endpoint.md) | Inji Certify | blocks every flow module (the harness works around it) | all issuer flow modules |
| [certify-credential-request-unknown-parameters.md](certify-credential-request-unknown-parameters.md) | Inji Certify | blocks issuance in the happy flow | `oid4vci-1_0-issuer-happy-flow` |
| [certify-proof-iss-rejected.md](certify-proof-iss-rejected.md) | Inji Certify | blocks issuance to authenticated clients | 4 issuer modules |
| [certify-credential-error-codes.md](certify-credential-error-codes.md) | Inji Certify | wrong error codes | 2 negative issuer modules |
| [certify-metadata-null-display-values.md](certify-metadata-null-display-values.md) | Inji Certify | invalid metadata | `oid4vci-1_0-issuer-metadata-test` |
| [certify-signed-metadata.md](certify-signed-metadata.md) | Inji Certify | optional feature missing | `oid4vci-1_0-issuer-metadata-test-signed` |
| [certify-optional-features.md](certify-optional-features.md) | Inji Certify | optional features missing (skips) | 3 issuer modules |
| [verify-request-signing-eddsa-only.md](verify-request-signing-eddsa-only.md) | Inji Verify | blocks the x509_san_dns configuration with HAIP wallets | every x509_san_dns module |
| [verify-request-object-iss.md](verify-request-object-iss.md) | Inji Verify | warning | every x509_san_dns module |
| [verify-request-uri-method-post.md](verify-request-uri-method-post.md) | Inji Verify | optional feature missing (skip) | `oid4vp-1final-verifier-request-uri-method-post` |
