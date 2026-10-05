"""The Inji Certify client: MOSIP error envelopes, idempotent seeding, offers and the offer URI."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
import respx

from inji_conformance import inji_certify
from inji_conformance.inji_certify import CertifyClient, CertifyError

BASE = "https://certify.inji.test:18450"
API = f"{BASE}/v1/certify"
CONFIG_ID = "InjiConformanceSdJwtVc"
OFFER_URI = f"{API}/credential-offer-data/5f0c0f6e-0c3b-4c6e-9d1c-7b0d7c5a1e11"
OFFER_URL = "openid-credential-offer://?credential_offer_uri=" + OFFER_URI.replace(":", "%3A").replace("/", "%2F")
DEFINITION = {
    "credentialConfigKeyId": CONFIG_ID,
    "credentialFormat": "dc+sd-jwt",
    "sdJwtVct": "urn:inji-conformance:vct:farmer:1",
    "signatureAlgo": "ES256",
    "vcTemplate": {"fullName": "${fullName}", "gender": "${gender}"},
}


def envelope(code: str, message: str = "") -> dict:
    """The body Inji Certify sends for most admin errors, with HTTP 200 or 404."""
    return {
        "responseTime": "2026-10-04T15:00:00.000Z",
        "response": None,
        "errors": [{"errorCode": code, "errorMessage": message}],
    }


def stored_configuration(**changes) -> dict:
    return {"credentialConfigKeyId": CONFIG_ID, "credentialFormat": "dc+sd-jwt", "status": "active", **changes}


# ---------------------------------------------------------------------------------------------------------------
# Envelope, offer URI, transaction code, request body
# ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (envelope("invalid_request", "boom"), [{"errorCode": "invalid_request", "errorMessage": "boom"}]),
        ({"response": None, "errors": ["plain text"]}, [{"errorMessage": "plain text"}]),
        ({"response": {"id": "x"}, "errors": []}, []),
        ({"response": {"id": "x"}, "errors": None}, []),
        ({"id": "x", "status": "active"}, []),
        (["not", "an", "envelope"], []),
        (None, []),
    ],
)
def test_envelope_errors(body, expected):
    assert inji_certify.envelope_errors(body) == expected


def test_offer_uri_is_url_decoded():
    assert inji_certify.credential_offer_uri(OFFER_URL) == OFFER_URI
    # Not encoded at all is read the same way.
    assert (
        inji_certify.credential_offer_uri(f"openid-credential-offer://?credential_offer_uri={OFFER_URI}") == OFFER_URI
    )


@pytest.mark.parametrize(
    ("offer_url", "message"),
    [
        # by value: the offer JSON itself, which the responder cannot hand over by reference
        ("openid-credential-offer://?credential_offer=%7B%22credential_issuer%22%3A%22x%22%7D", "no https"),
        ("openid-credential-offer://", "no https"),
        ("openid-credential-offer://?credential_offer_uri=", "no https"),
        ("openid-credential-offer://?credential_offer_uri=http%3A%2F%2Fcertify%2Foffer%2F1", "no https"),
        (OFFER_URI, "is not an openid-credential-offer:// URL"),
        ("", "is not an openid-credential-offer:// URL"),
    ],
)
def test_offer_without_a_usable_uri_is_refused(offer_url, message):
    with pytest.raises(CertifyError, match=message):
        inji_certify.credential_offer_uri(offer_url)


def test_tx_code_is_numeric_and_of_the_asked_length():
    for length in (4, 6, 8):
        code = inji_certify.new_tx_code(length)
        assert len(code) == length and code.isdigit()
    assert len({inji_certify.new_tx_code(8) for _ in range(20)}) > 1


@pytest.mark.parametrize("length", [0, 3, 9])
def test_tx_code_length_outside_what_certify_accepts(length):
    with pytest.raises(ValueError, match="4 to 8"):
        inji_certify.new_tx_code(length)


def test_configuration_request_sends_the_template_as_base64_json():
    request = inji_certify.configuration_request(DEFINITION)
    assert json.loads(base64.b64decode(request["vcTemplate"])) == DEFINITION["vcTemplate"]
    assert request["credentialConfigKeyId"] == CONFIG_ID
    assert isinstance(DEFINITION["vcTemplate"], dict)  # the definition itself is not changed


def test_configuration_request_keeps_a_template_that_is_already_text():
    encoded = base64.b64encode(b'{"a":"${a}"}').decode()
    assert inji_certify.configuration_request({**DEFINITION, "vcTemplate": encoded})["vcTemplate"] == encoded


@pytest.mark.parametrize("missing", ["credentialConfigKeyId", "credentialFormat", "vcTemplate"])
def test_configuration_request_names_the_missing_field(missing):
    definition = {key: value for key, value in DEFINITION.items() if key != missing}
    with pytest.raises(CertifyError, match=f"needs '{missing}'"):
        inji_certify.configuration_request(definition)


# ---------------------------------------------------------------------------------------------------------------
# Client calls
# ---------------------------------------------------------------------------------------------------------------


@respx.mock
def test_issuer_metadata_is_read_at_the_origin():
    respx.get(f"{BASE}/.well-known/openid-credential-issuer").mock(
        return_value=httpx.Response(200, json={"credential_issuer": BASE})
    )
    assert CertifyClient(BASE + "/").issuer_metadata() == {"credential_issuer": BASE}


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(502, text="Bad Gateway"),
        httpx.Response(200, text="<html>starting</html>"),
        httpx.Response(200, json={}),
    ],
    ids=["status", "not-json", "empty"],
)
def test_issuer_metadata_that_is_not_ready_is_a_certify_error(response):
    respx.get(f"{BASE}/.well-known/openid-credential-issuer").mock(return_value=response)
    with pytest.raises(CertifyError, match="issuer metadata"):
        CertifyClient(BASE).issuer_metadata()


@respx.mock
def test_get_configuration_returns_none_for_an_unknown_id():
    # Inji Certify answers an unknown id with HTTP 404 and an envelope (ExceptionHandlerAdvice.java,
    # CredentialConfigException).
    respx.get(f"{API}/credential-configurations/{CONFIG_ID}").mock(
        return_value=httpx.Response(404, json=envelope("invalid_request", "Configuration not found"))
    )
    assert CertifyClient(BASE).get_configuration(CONFIG_ID) is None


@respx.mock
def test_get_configuration_returns_the_stored_one_and_quotes_the_id_in_the_path():
    route = respx.get(f"{API}/credential-configurations/a%2Fb").mock(
        return_value=httpx.Response(200, json=stored_configuration(credentialConfigKeyId="a/b"))
    )
    assert CertifyClient(BASE).get_configuration("a/b")["status"] == "active"
    assert route.called


@respx.mock
def test_error_envelope_inside_http_200_is_a_failure():
    respx.get(f"{API}/credential-configurations/{CONFIG_ID}").mock(
        return_value=httpx.Response(200, json=envelope("config_not_active", "Configuration is not active"))
    )
    with pytest.raises(CertifyError, match="config_not_active: Configuration is not active") as caught:
        CertifyClient(BASE).get_configuration(CONFIG_ID)
    assert (caught.value.status, caught.value.code) == (200, "config_not_active")


@respx.mock
@pytest.mark.parametrize(
    "response",
    [httpx.Response(500, text="oops"), httpx.Response(200, json=stored_configuration(credentialConfigKeyId="other"))],
    ids=["status", "another-id"],
)
def test_get_configuration_refuses_other_answers(response):
    respx.get(f"{API}/credential-configurations/{CONFIG_ID}").mock(return_value=response)
    with pytest.raises(CertifyError):
        CertifyClient(BASE).get_configuration(CONFIG_ID)


@respx.mock
def test_add_configuration_posts_the_request_and_accepts_201():
    route = respx.post(f"{API}/credential-configurations").mock(
        return_value=httpx.Response(201, json={"id": CONFIG_ID, "status": "active"})
    )
    request = inji_certify.configuration_request(DEFINITION)
    assert CertifyClient(BASE).add_configuration(request) == {"id": CONFIG_ID, "status": "active"}
    assert json.loads(route.calls.last.request.content) == request


@respx.mock
def test_add_configuration_error_envelope_inside_http_200_keeps_the_code():
    respx.post(f"{API}/credential-configurations").mock(
        return_value=httpx.Response(200, json=envelope("dc_sd_jwt_mandatory_fields_missing", "Fields vct and ..."))
    )
    with pytest.raises(CertifyError) as caught:
        CertifyClient(BASE).add_configuration({})
    assert caught.value.code == "dc_sd_jwt_mandatory_fields_missing"
    assert "HTTP 200 dc_sd_jwt_mandatory_fields_missing" in str(caught.value)


@respx.mock
def test_create_offer_posts_claims_code_and_expiry():
    route = respx.post(f"{API}/pre-authorized-data").mock(
        return_value=httpx.Response(200, json={"credential_offer_uri": OFFER_URL})
    )
    offer = CertifyClient(BASE).create_offer(CONFIG_ID, {"fullName": "Asha"}, tx_code="123456", expires_in=600)
    assert json.loads(route.calls.last.request.content) == {
        "credential_configuration_id": CONFIG_ID,
        "claims": {"fullName": "Asha"},
        "expires_in": 600,
        "tx_code": "123456",
    }
    assert (offer.offer_url, offer.offer_uri, offer.tx_code) == (OFFER_URL, OFFER_URI, "123456")


@respx.mock
def test_create_offer_without_a_code_sends_none():
    route = respx.post(f"{API}/pre-authorized-data").mock(
        return_value=httpx.Response(200, json={"credential_offer_uri": OFFER_URL})
    )
    offer = CertifyClient(BASE).create_offer(CONFIG_ID, {}, tx_code=None, expires_in=0)
    assert json.loads(route.calls.last.request.content) == {"credential_configuration_id": CONFIG_ID, "claims": {}}
    assert offer.tx_code is None


@respx.mock
@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(200, json=envelope("invalid_request", "Unknown claims: [nickname]")), "invalid_request"),
        (httpx.Response(200, json={"something": "else"}), None),
        (httpx.Response(400, json=envelope("invalid_request", "Minimum expiry is 60 seconds")), "invalid_request"),
        (httpx.Response(502, text="Bad Gateway"), None),
    ],
    ids=["envelope-in-200", "no-offer-in-200", "http-400", "not-json"],
)
def test_create_offer_failures(response, code):
    respx.post(f"{API}/pre-authorized-data").mock(return_value=response)
    with pytest.raises(CertifyError, match="POST pre-authorized-data") as caught:
        CertifyClient(BASE).create_offer(CONFIG_ID, {"nickname": "x"}, tx_code="1234")
    assert (caught.value.status, caught.value.code) == (response.status_code, code)


# ---------------------------------------------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------------------------------------------


@respx.mock
def test_seed_creates_the_configuration_once_and_then_finds_it():
    stored: dict = {}

    def read(_request):
        if stored:
            return httpx.Response(200, json=stored_configuration())
        return httpx.Response(404, json=envelope("invalid_request", "Configuration not found"))

    def add(request):
        stored.update(json.loads(request.content))
        return httpx.Response(201, json={"id": CONFIG_ID, "status": "active"})

    respx.get(f"{API}/credential-configurations/{CONFIG_ID}").mock(side_effect=read)
    add_route = respx.post(f"{API}/credential-configurations").mock(side_effect=add)
    client = CertifyClient(BASE)

    first = inji_certify.seed(client, DEFINITION)
    second = inji_certify.seed(client, DEFINITION)

    assert (first.created, second.created) == (True, False)
    assert first.message() == f"seed certify: credential configuration {CONFIG_ID} created"
    assert second.message() == f"seed certify: credential configuration {CONFIG_ID} already present"
    assert add_route.call_count == 1
    assert json.loads(base64.b64decode(stored["vcTemplate"])) == DEFINITION["vcTemplate"]


@respx.mock
def test_seed_refuses_an_existing_configuration_of_another_format():
    respx.get(f"{API}/credential-configurations/{CONFIG_ID}").mock(
        return_value=httpx.Response(200, json=stored_configuration(credentialFormat="ldp_vc"))
    )
    add_route = respx.post(f"{API}/credential-configurations").mock(return_value=httpx.Response(201, json={}))
    with pytest.raises(CertifyError, match="exists with format ldp_vc, not dc\\+sd-jwt"):
        inji_certify.seed(CertifyClient(BASE), DEFINITION)
    assert not add_route.called


@respx.mock
def test_seed_explains_a_vct_that_another_configuration_already_uses():
    respx.get(f"{API}/credential-configurations/{CONFIG_ID}").mock(
        return_value=httpx.Response(404, json=envelope("invalid_request"))
    )
    respx.post(f"{API}/credential-configurations").mock(
        return_value=httpx.Response(200, json=envelope("dc_sd_jwt_config_exists", "Configuration already exists"))
    )
    with pytest.raises(
        CertifyError, match=f"another configuration for vct urn:inji-conformance:vct:farmer:1.*{CONFIG_ID}"
    ):
        inji_certify.seed(CertifyClient(BASE), DEFINITION)


@respx.mock
def test_seed_passes_other_creation_errors_on():
    respx.get(f"{API}/credential-configurations/{CONFIG_ID}").mock(
        return_value=httpx.Response(404, json=envelope("invalid_request"))
    )
    respx.post(f"{API}/credential-configurations").mock(
        return_value=httpx.Response(200, json=envelope("unsupported_format", "Unsupported credential format"))
    )
    with pytest.raises(CertifyError) as caught:
        inji_certify.seed(CertifyClient(BASE), DEFINITION)
    assert caught.value.code == "unsupported_format"


@respx.mock
def test_seed_fails_when_the_new_configuration_cannot_be_read_back():
    respx.get(f"{API}/credential-configurations/{CONFIG_ID}").mock(
        return_value=httpx.Response(404, json=envelope("invalid_request"))
    )
    respx.post(f"{API}/credential-configurations").mock(return_value=httpx.Response(201, json={"id": CONFIG_ID}))
    with pytest.raises(CertifyError, match="accepted but cannot be read back"):
        inji_certify.seed(CertifyClient(BASE), DEFINITION)
