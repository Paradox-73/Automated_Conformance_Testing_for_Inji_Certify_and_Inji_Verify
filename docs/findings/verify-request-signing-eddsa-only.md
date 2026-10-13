# Inji Verify signs request objects only with Ed25519, and its bundled test keystore is self-signed

## Summary

Inji Verify takes the first EdDSA key of its PKCS#12 keystore (`P12KeyExtractor`, "No EdDSA key entry found in
the P12 file" otherwise) and signs every request object with `alg: EdDSA`. Two consequences for wallets:

1. HAIP and many wallets expect ES256 request objects; an EdDSA-only verifier cannot serve them. The
   conformance suite release-v5.3.1 cannot verify the EdDSA signature against the `x5c` certificate either
   ("Error verifying JWT signature using x5c leaf certificate"), although the signature is valid: it verifies
   with `openssl pkeyutl -verify` against the same certificate (measured 2026-10-14). The suite part is listed in
   [../suite-limitations.md](../suite-limitations.md).
2. The keystore bundled in the image (`sample-keystore/test.p12`) holds a self-signed certificate, which the suite
   rejects ("Leaf certificate in x5c chain must not be self-signed"). The harness therefore gives Inji Verify a key
   whose certificate the run's test CA issued (`compose/pki/generate.py`), without the CA in the chain ("Trust
   anchor (self-signed root CA) must not be included in x5c chain").

## Affected version

`injistackqa/inji-verify-service:1.0.x@sha256:a9b81fd4a1b97ee8d78bde670634d1bf1bd880d128c08239c5cf25c927891eef` (Inji Verify 1.0 line, `verify-core` `1.0.0-alpha.2-SNAPSHOT`), configured as in `docker-compose.yml` (service `verify-service`).

## Spec reference

OpenID4VP 1.0, the `x509_san_dns` client identifier prefix (`x5c`); the suite logs `OID4VP-1FINAL-5.9.3`. HAIP (OpenID4VC High Assurance Interoperability Profile) for ES256.

## Suite condition

`ValidateRequestObjectSignatureAgainstX5cHeader` in block "Authorization endpoint" of every module of the
`x509_san_dns` configuration.

## Steps

<!-- run 2026-10-14 -->
```bash
./run-conformance.sh --component verify --runner-only --template verify.oid4vp-1final-verifier-x509-san-dns
```

## Expected

A request object the wallet can verify: ES256 (or another algorithm the wallet announces) with a certificate chain
that ends below a trust anchor the wallet knows.

## Actual

`alg: EdDSA` only; with the bundled keystore a self-signed leaf certificate.

## Evidence

Run `20261013T222732Z-0cc34f`, [`docs/evidence/2026-10-13-20261013T222732Z-0cc34f/`](../evidence/2026-10-13-20261013T222732Z-0cc34f/); first measured 2026-10-14.

## Proposed fix

Support ES256 request signing keys (an EC P-256 entry in the keystore, chosen by configuration or by the wallet's
`request_object_signing_alg_values_supported`), and document that deployments must replace the sample keystore
with a CA-issued certificate.
