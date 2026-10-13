"""Inji Certify: the issuer back-office calls the harness makes before and during the issuer plan.

Two jobs a person (the issuer's operator) normally does by hand:

1. **Seeding**: the issuer plan asks for an SD-JWT VC (``dc+sd-jwt``), and the compose stack only seeds an
   ``ldp_vc`` configuration (upstream ``certify_init.sql``). ``seed`` adds the ``dc+sd-jwt`` credential configuration
   once, through ``/v1/certify/credential-configurations``, and recognises it on later calls (idempotent).
2. **Credential offers**: each issuer test waits for an offer. ``create_offer`` asks Certify for a pre-authorized
   offer (``POST /v1/certify/pre-authorized-data``) with the claims to issue and a transaction code; the handoff
   responder hands the offer URI to the suite's wallet.

Certify's admin APIs report many errors as HTTP 200 with a MOSIP envelope ``{"response": null, "errors": [...]}``
(measured on 2026-10-04 against image ``d6635da``), so every call checks the body for ``errors`` and never trusts the
status code alone.

Sources (inji-certify ``release-1.0.x``): ``CredentialConfigController.java``, ``PreAuthorizedCodeController.java``,
``PreAuthorizedCodeService.java`` (offer URI format, ``tx_code`` 4-8 letters or digits), ``SD_JWT_Support.md``.
"""

from __future__ import annotations

import base64
import copy
import dataclasses
import json
import secrets
import urllib.parse
from collections.abc import Mapping
from typing import Any

import httpx

OFFER_SCHEME = "openid-credential-offer://"


class CertifyError(RuntimeError):
    """Inji Certify refused or failed a request. ``status`` is the HTTP status, ``code`` the MOSIP error code."""

    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


def envelope_errors(body: Any) -> list[dict[str, Any]]:
    """The ``errors`` list of a MOSIP response envelope; empty for a successful or non-envelope body."""
    if isinstance(body, Mapping) and isinstance(body.get("errors"), list):
        return [e if isinstance(e, dict) else {"errorMessage": str(e)} for e in body["errors"] if e]
    return []


def _describe(errors: list[dict[str, Any]]) -> str:
    return "; ".join(f"{e.get('errorCode', '?')}: {e.get('errorMessage', '')}".strip() for e in errors)


def credential_offer_uri(offer_url: str) -> str:
    """The ``credential_offer_uri`` parameter of an ``openid-credential-offer://?credential_offer_uri=...`` URL."""
    if not offer_url.startswith(OFFER_SCHEME):
        raise CertifyError(f"offer is not an {OFFER_SCHEME} URL: {offer_url[:120]}")
    query = urllib.parse.urlsplit(offer_url).query
    values = urllib.parse.parse_qs(query).get("credential_offer_uri")
    if not values or not values[0].startswith("https://"):
        raise CertifyError(f"offer has no https credential_offer_uri: {offer_url[:200]}")
    return values[0]


def new_tx_code(length: int) -> str:
    """A numeric transaction code; Certify accepts 4 to 8 letters or digits (``PreAuthorizedRequest.java``)."""
    if not 4 <= length <= 8:
        raise ValueError("Inji Certify accepts transaction codes of 4 to 8 characters")
    return "".join(secrets.choice("0123456789") for _ in range(length))


def configuration_request(definition: Mapping[str, Any]) -> dict[str, Any]:
    """The body of ``POST /credential-configurations`` for a plan template's ``seed.credential_configuration``.

    The template keeps ``vcTemplate`` readable as a JSON object; Certify wants it as base64 of the JSON text
    (``VelocityTemplatingEngineImpl`` decodes it at issuance; a raw JSON string is accepted at creation but fails at
    issuance with ``json_processing_error``, measured 2026-10-04).
    """
    body = copy.deepcopy(dict(definition))
    template = body.get("vcTemplate")
    if isinstance(template, Mapping):
        text = json.dumps(template, separators=(",", ":"), ensure_ascii=False)
        body["vcTemplate"] = base64.b64encode(text.encode("utf-8")).decode("ascii")
    for key in ("credentialConfigKeyId", "credentialFormat", "vcTemplate"):
        if not isinstance(body.get(key), str) or not body[key]:
            raise CertifyError(f"seed.credential_configuration needs '{key}'")
    return body


@dataclasses.dataclass(frozen=True)
class Offer:
    """A pre-authorized credential offer Certify created."""

    offer_url: str  # openid-credential-offer://?credential_offer_uri=...
    offer_uri: str  # https URL the wallet fetches the offer JSON from
    tx_code: str | None


class CertifyClient:
    """The Inji Certify APIs the harness uses. ``base_url`` is the issuer origin, for example
    ``https://certify.inji.test:18450``; the APIs are under ``/v1/certify``."""

    def __init__(self, base_url: str, *, verify: bool | str = True, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api = self.base_url + "/v1/certify"
        self._http = httpx.Client(verify=verify, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def issuer_metadata(self) -> dict[str, Any]:
        """``GET /.well-known/openid-credential-issuer`` at the issuer origin."""
        response = self._http.get(f"{self.base_url}/.well-known/openid-credential-issuer")
        if response.status_code != 200:
            raise CertifyError(f"issuer metadata: HTTP {response.status_code}", response.status_code)
        body = _json(response)
        if not isinstance(body, dict) or not body:
            raise CertifyError(f"issuer metadata: not a JSON object: {response.text[:200]}", response.status_code)
        return body

    def as_metadata_shim(self) -> str | None:
        """The harness proxy's note when it changed the authorization server metadata (``X-Harness-Shim``), else None.

        See ``compose/tls-proxy/certify-as-metadata/``. A failed request counts as no change.
        """
        try:
            response = self._http.get(f"{self.base_url}/.well-known/oauth-authorization-server")
        except httpx.HTTPError:
            return None
        return response.headers.get("x-harness-shim") or None

    def get_configuration(self, config_id: str) -> dict[str, Any] | None:
        """The active configuration ``config_id``, or None when Certify has none with that id."""
        response = self._http.get(f"{self.api}/credential-configurations/{urllib.parse.quote(config_id, safe='')}")
        body = _json(response)
        errors = envelope_errors(body)
        if response.status_code == 404:
            return None
        if errors or response.status_code != 200:
            raise CertifyError(
                f"GET credential-configurations/{config_id}: HTTP {response.status_code} "
                f"{_describe(errors) or response.text[:200]}",
                response.status_code,
                errors[0].get("errorCode") if errors else None,
            )
        if not isinstance(body, dict) or body.get("credentialConfigKeyId") != config_id:
            raise CertifyError(f"GET credential-configurations/{config_id}: unexpected body {str(body)[:200]}")
        return body

    def add_configuration(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """``POST /credential-configurations``; the response body (``id``, ``status``)."""
        response = self._http.post(f"{self.api}/credential-configurations", json=dict(request))
        body = _json(response)
        errors = envelope_errors(body)
        if errors or response.status_code not in (200, 201):
            raise CertifyError(
                f"POST credential-configurations: HTTP {response.status_code} "
                f"{_describe(errors) or response.text[:300]}",
                response.status_code,
                errors[0].get("errorCode") if errors else None,
            )
        return body if isinstance(body, dict) else {}

    def create_offer(
        self, config_id: str, claims: Mapping[str, Any], *, tx_code: str | None, expires_in: int = 600
    ) -> Offer:
        """``POST /pre-authorized-data``: a fresh pre-authorized offer for ``claims``."""
        body: dict[str, Any] = {"credential_configuration_id": config_id, "claims": dict(claims)}
        if expires_in:
            body["expires_in"] = expires_in
        if tx_code:
            body["tx_code"] = tx_code
        response = self._http.post(f"{self.api}/pre-authorized-data", json=body)
        data = _json(response)
        errors = envelope_errors(data)
        offer_url = data.get("credential_offer_uri") if isinstance(data, dict) else None
        if errors or response.status_code != 200 or not isinstance(offer_url, str):
            raise CertifyError(
                f"POST pre-authorized-data: HTTP {response.status_code} {_describe(errors) or response.text[:300]}",
                response.status_code,
                errors[0].get("errorCode") if errors else None,
            )
        return Offer(offer_url=offer_url, offer_uri=credential_offer_uri(offer_url), tx_code=tx_code)


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


@dataclasses.dataclass(frozen=True)
class SeedOutcome:
    config_id: str
    created: bool  # False: it was already present

    def message(self) -> str:
        state = "created" if self.created else "already present"
        return f"seed certify: credential configuration {self.config_id} {state}"


def seed(client: CertifyClient, definition: Mapping[str, Any]) -> SeedOutcome:
    """Make sure the credential configuration in ``definition`` exists; create it when it does not.

    An existing configuration with the same id is left as it is (it may hold data a person added). A different
    configuration with the same ``vct`` makes Certify refuse the creation (``dc_sd_jwt_config_exists``); that is
    reported, since the plan would then request an id Certify does not know.
    """
    request = configuration_request(definition)
    config_id = request["credentialConfigKeyId"]
    existing = client.get_configuration(config_id)
    if existing is not None:
        expected = request.get("credentialFormat")
        if existing.get("credentialFormat") not in (None, expected):
            raise CertifyError(
                f"credential configuration {config_id} exists with format {existing.get('credentialFormat')}, "
                f"not {expected}; delete it or choose another id"
            )
        return SeedOutcome(config_id, created=False)
    try:
        client.add_configuration(request)
    except CertifyError as error:
        if error.code and error.code.endswith("_config_exists"):
            raise CertifyError(
                f"Inji Certify already has another configuration for vct {request.get('sdJwtVct')} "
                f"({error}); the plan needs id {config_id}"
            ) from error
        raise
    if client.get_configuration(config_id) is None:
        raise CertifyError(f"credential configuration {config_id} was accepted but cannot be read back")
    return SeedOutcome(config_id, created=True)
