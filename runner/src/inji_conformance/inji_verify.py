"""Inji Verify: create an authorization request and turn it into the query string a wallet receives.

A person testing Inji Verify by hand clicks "verify" in the Inji Verify page, which calls the backend for an
authorization request and shows the result as an ``openid4vp://authorize?<query>`` QR code. The harness does the
same without a browser:

1. ``POST <verify>/v2/vp-request`` with the client id and DCQL query (``create_vp_request``);
2. build the query string exactly as the Inji Verify SDK does (``authorization_query``), so the suite sees what
   a real wallet would see;
3. hand the query string to the suite's authorization endpoint (``inji_conformance.handoff``).

The SDK code reproduced here is ``getAuthorizationRequestParams`` in
``inji-verify-sdk/src/components/openid4vp-verification/OpenID4VPVerification.tsx`` (lines 56-83 on
release-1.0.x, commit 6a6ab3b) with ``VP_FORMATS_SUPPORTED`` from ``inji-verify-sdk/src/utils/constants.ts``.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

# client_id prefixes for which the SDK adds client_metadata to a by-value request (utils.ts isSignedRequestScheme,
# isRedirectUriClientId).
_SIGNED_PREFIXES = ("decentralized_identifier:", "x509_san_dns:")
_REDIRECT_URI_PREFIX = "redirect_uri:"

# constants.ts VP_FORMATS_SUPPORTED, in the same key order (the order is visible in the serialised JSON).
VP_FORMATS_SUPPORTED: dict[str, Any] = {
    "ldp_vp": {"proof_type": ["Ed25519Signature2018", "Ed25519Signature2020", "RsaSignature2018"]},
    "dc+sd-jwt": {
        "sd-jwt_alg_values": ["RS256", "ES256", "ES256K", "EdDSA"],
        "kb-jwt_alg_values": ["RS256", "ES256", "ES256K", "EdDSA"],
    },
    "vc+sd-jwt": {
        "sd-jwt_alg_values": ["RS256", "ES256", "ES256K", "EdDSA"],
        "kb-jwt_alg_values": ["RS256", "ES256", "ES256K", "EdDSA"],
    },
}

# Bytes the WHATWG application/x-www-form-urlencoded serializer leaves as they are (URLSearchParams.toString()).
_FORM_SAFE = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789*-._")


class VerifyError(RuntimeError):
    """Inji Verify refused or failed a request; ``status`` is the HTTP status when there was a response."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def form_urlencode(pairs: Sequence[tuple[str, str]]) -> str:
    """Serialise name-value pairs as ``URLSearchParams.toString()`` does in a browser.

    This differs from ``urllib.parse.urlencode``: ``~`` is percent-encoded and ``*`` is not (WHATWG URL standard,
    application/x-www-form-urlencoded serializer). Spaces become ``+``.
    """

    def encode(text: str) -> str:
        out = []
        for byte in text.encode("utf-8"):
            if byte in _FORM_SAFE:
                out.append(chr(byte))
            elif byte == 0x20:
                out.append("+")
            else:
                out.append(f"%{byte:02X}")
        return "".join(out)

    return "&".join(f"{encode(name)}={encode(value)}" for name, value in pairs)


def _js_json(value: Any) -> str:
    """``JSON.stringify(value)``: no spaces, keys in insertion order, non-ASCII kept as is."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def authorization_query(client_id: str, response: Mapping[str, Any]) -> str:
    """The query string the Inji Verify SDK puts after ``openid4vp://authorize?``.

    ``response`` is the body of ``POST /v2/vp-request`` (``VPRequestResponseDto``). A request by reference
    (``requestUri`` present, as for ``x509_san_dns``) gives ``client_id`` and ``request_uri`` only; a request by
    value gives the authorization parameters themselves.
    """
    params: list[tuple[str, str]] = [("client_id", client_id)]
    details = response.get("authorizationDetails")
    if response.get("requestUri"):
        params.append(("request_uri", str(response["requestUri"])))
    elif details:
        params += [
            ("state", str(response.get("requestId"))),
            ("response_mode", str(details.get("responseMode"))),
            ("response_type", str(details.get("responseType"))),
            ("nonce", str(details.get("nonce"))),
            ("response_uri", str(details.get("responseUri"))),
        ]
        if details.get("dcqlQuery"):
            params.append(("dcql_query", _js_json(details["dcqlQuery"])))
        if client_id.startswith(_SIGNED_PREFIXES) or client_id.startswith(_REDIRECT_URI_PREFIX):
            params.append(("client_metadata", _js_json({"vp_formats_supported": VP_FORMATS_SUPPORTED})))
    return form_urlencode(params)


def generate_nonce() -> str:
    """A fresh nonce as the SDK makes it (``generateNonce`` in ``utils/api.ts``): 32 random bytes, base64url.

    Inji Verify puts this nonce into the request object, and the suite checks its entropy
    (``VP1FinalEnsureMinimumNonceEntropy``), so a shorter nonce would be reported against Inji Verify.
    """
    return secrets.token_urlsafe(32)


class VerifyClient:
    """The Inji Verify backend API the harness uses (base URL ends in ``/v1/verify``)."""

    def __init__(self, base_url: str, *, verify: bool | str = True, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(verify=verify, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def health(self) -> int:
        """HTTP status of the actuator health endpoint."""
        return self._http.get(f"{self.base_url}/actuator/health").status_code

    def create_vp_request(
        self, client_id: str, dcql_query: Mapping[str, Any], response_mode: str | None = None
    ) -> dict[str, Any]:
        """``POST /v2/vp-request``; the response body (transactionId, requestId, requestUri, ...)."""
        body: dict[str, Any] = {"clientId": client_id, "nonce": generate_nonce(), "dcqlQuery": dcql_query}
        if response_mode:
            body["responseMode"] = response_mode
        response = self._http.post(f"{self.base_url}/v2/vp-request", json=body)
        if response.status_code != 201:
            raise VerifyError(
                f"POST /v2/vp-request returned HTTP {response.status_code}: {response.text[:300]}",
                response.status_code,
            )
        return response.json()

    def vp_result(self, transaction_id: str) -> dict[str, Any] | None:
        """``GET /vp-result/{transactionId}``; None when Inji Verify has no result for it."""
        response = self._http.get(f"{self.base_url}/vp-result/{transaction_id}")
        if response.status_code != 200:
            return None
        body = response.json()
        return body if isinstance(body, dict) else None
