# Inji Certify's authorization server metadata has no authorization_endpoint

## Summary

Inji Certify acts as its own OAuth authorization server, and its metadata at
`/.well-known/oauth-authorization-server` lists the `authorization_code` grant and the `code` response type, but has
no `authorization_endpoint`. The class that builds the document (`OAuthAuthorizationServerMetadataDTO` in
`certify-core`) has no such field, so no configuration can add one. The conformance suite reads the authorization
server metadata at the start of every issuer flow and stops at once without an `authorization_endpoint`, also in
the pre-authorized code flow, which never calls it. With the metadata as Inji Certify serves it, 13 of the 15 modules
of the issuer plan stop at that first condition and nothing about issuance can be measured.

The harness therefore inserts a placeholder `authorization_endpoint` in its TLS proxy by default
(`CERTIFY_AS_METADATA=add-authorization-endpoint`, `compose/tls-proxy/certify-as-metadata/`), marks the response
with `X-Harness-Shim`, and records that in every `results.json` as a `workarounds` entry named
`certify-as-metadata-authorization-endpoint`. The runner's gate line, `summary.html` and `summary.md` state it next to
the gate result. `CERTIFY_AS_METADATA=as-is` turns the workaround off and reproduces this finding
([configuration](../configuration.md#inji-certify-metadata-workaround)).

## Affected version

`injistackqa/inji-certify-with-plugins:develop@sha256:b5022884fb308fe8f697d11a2f6256714a97cec3188dbc5ed8b9aa59d1cacf5c`
(Inji Certify 1.0 line, `certify-service` `1.0.0-beta.1-SNAPSHOT`), configured as in `compose/certify/` (Certify as
its own authorization server, `mosip.certify.oauth.*`).

## Spec reference

RFC 8414 section 2: `authorization_endpoint` is required unless no grant type that uses it is supported, and
the metadata lists `authorization_code`. OpenID4VCI 1.0 uses RFC 8414 metadata for the authorization servers named in
`authorization_servers`.

## Suite condition

`CheckServerConfiguration`: "Couldn't find required component" (`required: authorization_endpoint`), first block of
every flow module of `oid4vci-1_0-issuer-test-plan`; the modules end INTERRUPTED with result FAILED.

## Steps

<!-- run 2026-10-14 -->
```bash
CERTIFY_AS_METADATA=as-is ./run-conformance.sh --component certify --runner-only --no-gate
```

## Expected

The metadata names an `authorization_endpoint` (Inji Certify has an interactive authorization endpoint), or does not
list the `authorization_code` grant when the deployment offers only pre-authorized codes.

## Actual

```text
{"issuer":"https://certify.inji.test:18450","token_endpoint":"https://certify.inji.test:18450/v1/certify/oauth/token",
 "jwks_uri":"...","grant_types_supported":["authorization_code","urn:ietf:params:oauth:grant-type:pre-authorized_code"],
 "response_types_supported":["code"],"code_challenge_methods_supported":["S256"],
 "interactive_authorization_endpoint":"https://certify.inji.test:18450/v1/certify/oauth/iae",
 "require_interactive_authorization_request":true}
```

Run `20261013T222630Z-e4420c` (2026-10-14): 13 modules INTERRUPTED at `CheckServerConfiguration`; only the two
metadata modules got further.

## Evidence

[`docs/evidence/2026-10-13-20261013T222630Z-e4420c/`](../evidence/2026-10-13-20261013T222630Z-e4420c/), first
measured 2026-10-14 (run `20261013T204142Z-e9e602`, before the harness could add the field).

## Proposed fix

Add `authorization_endpoint` (configurable, for example `mosip.certify.oauth.authorization-endpoint`) to the
metadata class, and build `grant_types_supported` and `response_types_supported` from what the deployment really
offers, so that a pre-authorized-only deployment does not announce `authorization_code`.
