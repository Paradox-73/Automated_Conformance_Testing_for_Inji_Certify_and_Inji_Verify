### Inji conformance: gate passed with 1 workaround

Run `20261025T105438Z-68b2e2`

- Workaround (certify): The TLS proxy changed Inji Certify's OAuth authorization server metadata: authorization_endpoint added by the TLS proxy. Covers the Inji finding `docs/findings/certify-as-metadata-authorization-endpoint.md`; turn it off with `CERTIFY_AS_METADATA=as-is`.

| Component | Modules | Conforms | Known gap | Regression | Not applicable | Stale benchmark |
|---|---:|---:|---:|---:|---:|---:|
| certify | 15 | 3 | 9 | 0 | 3 | 0 |
