# Inji Verify's signed request object has an iss that differs from its client_id

## Summary

With an `x509_san_dns` client id, Inji Verify signs its request object with `"client_id":
"x509_san_dns:verify.inji.test"` and `"iss": "verify.inji.test"`. The suite warns that `iss` is present but does
not match the client id. A wallet that checks `iss` against `client_id` may refuse the request.

## Affected version

`injistackqa/inji-verify-service:1.0.x@sha256:a9b81fd4a1b97ee8d78bde670634d1bf1bd880d128c08239c5cf25c927891eef` (Inji Verify 1.0 line, `verify-core` `1.0.0-alpha.2-SNAPSHOT`), configured as in `docker-compose.yml` (service `verify-service`), with the request signing key from `pki-init` (SAN `verify.inji.test`).

## Spec reference

OpenID4VP 1.0, the authorization request (`client_id` and the signed request object); the suite logs
`OID4VP-1FINAL-5`.

## Suite condition

`ValidateRequestObjectIssIfPresent` (warning) in block "Authorization endpoint", every module of the verifier plan
with `client_id_prefix=x509_san_dns` and `request_method=request_uri_signed` (template
`verify.oid4vp-1final-verifier-x509-san-dns`).

## Steps

<!-- run 2026-10-14 -->
```bash
./run-conformance.sh --component verify --runner-only --template verify.oid4vp-1final-verifier-x509-san-dns
```

## Expected

`iss` left out, or equal to `client_id` (`x509_san_dns:verify.inji.test`).

## Actual

Request object claims (decoded from `GET /v1/verify/v2/vp-request/<id>`):

```text
{"iss": "verify.inji.test", "client_id": "x509_san_dns:verify.inji.test", "aud": "https://self-issued.me/v2", ...}
```

## Evidence

Run `20261013T222732Z-0cc34f`, [`docs/evidence/2026-10-13-20261013T222732Z-0cc34f/`](../evidence/2026-10-13-20261013T222732Z-0cc34f/) (every module carries the warning);
first measured 2026-10-14.

## Proposed fix

Set `iss` to the full client id, or leave it out of the request object.
