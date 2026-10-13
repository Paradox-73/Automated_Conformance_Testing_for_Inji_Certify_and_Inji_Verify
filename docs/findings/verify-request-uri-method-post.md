# Inji Verify does not offer request_uri_method=post

## Summary

The suite's module `oid4vp-1final-verifier-request-uri-method-post` needs an authorization request with
`request_uri_method=post`, so that the wallet can send its metadata when it fetches the request object. Inji
Verify never adds the parameter, and the suite skips the module.

## Affected version

`injistackqa/inji-verify-service:1.0.x@sha256:a9b81fd4a1b97ee8d78bde670634d1bf1bd880d128c08239c5cf25c927891eef` (Inji Verify 1.0 line, `verify-core` `1.0.0-alpha.2-SNAPSHOT`), configured as in `docker-compose.yml` (service `verify-service`).

## Spec reference

OpenID4VP 1.0, the `request_uri_method` parameter of the authorization request.

## Suite condition

Result SKIPPED for `oid4vp-1final-verifier-request-uri-method-post` (configuration
`verify.oid4vp-1final-verifier-x509-san-dns`; with the default `redirect_uri` configuration the request is
passed by value and the module runs, result REVIEW, verdict conforms).

## Steps

<!-- run 2026-10-14 -->
```bash
./run-conformance.sh --component verify --runner-only --template verify.oid4vp-1final-verifier-x509-san-dns
```

## Expected

Either `request_uri_method=post` with a `request_uri` that accepts POST, or the module skipped (today's
behaviour, listed as an expected skip).

## Actual

The module ends FINISHED with result SKIPPED; verdict `not_applicable`.

## Evidence

Run `20261013T222732Z-0cc34f`, [`docs/evidence/2026-10-13-20261013T222732Z-0cc34f/`](../evidence/2026-10-13-20261013T222732Z-0cc34f/); first measured 2026-10-14.

## Proposed fix

Optional: support `request_uri_method=post` (accept POST with `wallet_metadata` at the request URI).
