"""The handoff responder against a fake suite and mocked Inji Verify and Inji Certify."""

from __future__ import annotations

import itertools
import json
import urllib.parse

import httpx
import pytest
import respx

from inji_conformance.handoff import (
    AuthorizationRequestHandoff,
    BrowserVisitHandoff,
    CredentialOfferHandoff,
    Responder,
    StartTestHandoff,
    TestView,
    _with_query,
)
from inji_conformance.inji_certify import CertifyClient
from inji_conformance.inji_verify import VerifyClient
from inji_conformance.model import HandoffKind
from inji_conformance.suite import SuiteClient

SUITE = "https://localhost.emobix.co.uk:18443"
VERIFY = "https://verify.inji.test:18451/v1/verify"
ALIAS = "inji-verify-20261004T193000Z-abc123"
AUTHZ = f"{SUITE}/test/a/{ALIAS}/authorize"
DCQL = {"credentials": [{"id": "pid", "format": "dc+sd-jwt", "meta": {"vct_values": ["urn:eudi:pid:1"]}}]}


def waiting(test_id="t1", **runner) -> TestView:
    return TestView(test_id, "oid4vp-1final-verifier-happy-flow", "WAITING", runner)


def authorization_handoff() -> AuthorizationRequestHandoff:
    return AuthorizationRequestHandoff(
        SuiteClient(SUITE), VerifyClient(VERIFY), "x509_san_dns:test.example.com", DCQL, "direct_post"
    )


@respx.mock
def test_authorization_request_is_delivered_once_with_the_sdk_query():
    respx.post(f"{VERIFY}/v2/vp-request").mock(
        return_value=httpx.Response(
            201, json={"transactionId": "tx1", "requestId": "rq1", "requestUri": f"{VERIFY}/v2/vp-request/rq1"}
        )
    )
    suite_route = respx.get(AUTHZ).mock(return_value=httpx.Response(302, headers={"Location": "https://x"}))
    handoff = authorization_handoff()
    test = waiting(exposed={"authorization_endpoint": AUTHZ})

    assert handoff.wants(test)
    record = handoff.deliver(test)

    query = urllib.parse.parse_qs(suite_route.calls.last.request.url.query.decode())
    assert query == {"client_id": ["x509_san_dns:test.example.com"], "request_uri": [f"{VERIFY}/v2/vp-request/rq1"]}
    assert (record.kind, record.http_status, record.error) == (HandoffKind.AUTHORIZATION_REQUEST, 302, None)
    assert record.data == {"transaction_id": "tx1", "request_id": "rq1"}
    assert not handoff.wants(test)  # one request per test


@respx.mock
def test_failed_vp_request_is_recorded_and_retried_up_to_the_limit():
    respx.post(f"{VERIFY}/v2/vp-request").mock(return_value=httpx.Response(500, text="boom"))
    handoff = authorization_handoff()
    test = waiting(exposed={"authorization_endpoint": AUTHZ})
    records = []
    while handoff.wants(test):
        records.append(handoff.deliver(test))
    assert len(records) == 3
    assert all(r.http_status is None and "HTTP 500" in r.error for r in records)


def test_authorization_handoff_ignores_tests_without_the_endpoint():
    handoff = authorization_handoff()
    assert not handoff.wants(waiting(exposed={}))
    assert not handoff.wants(TestView("t1", "m", "CONFIGURED", {"exposed": {"authorization_endpoint": AUTHZ}}))


@respx.mock
def test_browser_urls_are_visited_and_marked():
    respx.get("https://verify.inji.test:18451/cb").mock(return_value=httpx.Response(200))
    mark = respx.post(f"{SUITE}/api/runner/browser/t1/visit").mock(return_value=httpx.Response(204))
    handoff = BrowserVisitHandoff(SuiteClient(SUITE))
    test = waiting(browser={"urls": ["https://verify.inji.test:18451/cb"], "visited": []})
    assert handoff.wants(test)
    record = handoff.deliver(test)
    assert (record.kind, record.http_status) == (HandoffKind.BROWSER_VISIT, 200)
    assert mark.calls.last.request.url.params["url"] == "https://verify.inji.test:18451/cb"
    assert not handoff.wants(test)


@respx.mock
def test_configured_test_is_started_only_after_the_grace_period():
    start = respx.post(f"{SUITE}/api/runner/t1").mock(return_value=httpx.Response(200, json={}))
    now = [100.0]
    handoff = StartTestHandoff(SuiteClient(SUITE), grace_s=5, clock=lambda: now[0])
    test = TestView("t1", "m", "CONFIGURED", {})
    assert not handoff.wants(test)
    now[0] = 106.0
    assert handoff.wants(test)
    assert handoff.deliver(test).kind is HandoffKind.START_TEST
    assert start.called
    assert not handoff.wants(test)


@respx.mock
def test_responder_answers_only_its_own_alias(tmp_path):
    respx.get(f"{SUITE}/api/runner/running").mock(return_value=httpx.Response(200, json=["mine", "other"]))
    respx.get(f"{SUITE}/api/info/mine").mock(
        return_value=httpx.Response(
            200, json={"testName": "oid4vp-1final-verifier-happy-flow", "alias": ALIAS, "status": "WAITING"}
        )
    )
    other_info = respx.get(f"{SUITE}/api/info/other").mock(
        return_value=httpx.Response(200, json={"testName": "x", "alias": "someone-else", "status": "WAITING"})
    )
    respx.get(f"{SUITE}/api/runner/mine").mock(
        return_value=httpx.Response(200, json={"exposed": {"authorization_endpoint": AUTHZ}, "browser": {}})
    )
    respx.post(f"{VERIFY}/v2/vp-request").mock(
        return_value=httpx.Response(201, json={"transactionId": "tx", "requestId": "rq", "requestUri": "https://r"})
    )
    respx.get(AUTHZ).mock(return_value=httpx.Response(200))
    lines: list[str] = []
    log = tmp_path / "handoffs.jsonl"
    responder = Responder(SuiteClient(SUITE), ALIAS, [authorization_handoff()], log_path=log, echo=lines.append)

    responder.poll_once()
    responder.poll_once()

    assert [r.test_id for r in responder.records] == ["mine"]
    assert other_info.call_count == 1  # another run's test is looked up once, then ignored
    assert responder.records_for("mine")[0].http_status == 200
    assert json.loads(log.read_text().splitlines()[0])["kind"] == "authorization_request"
    assert lines[0].startswith("handoff authorization_request oid4vp-1final-verifier-happy-flow (mine): HTTP 200")


@respx.mock
def test_responder_thread_survives_a_failing_poll():
    respx.get(f"{SUITE}/api/runner/running").mock(side_effect=httpx.ConnectError("refused"))
    lines: list[str] = []
    responder = Responder(SuiteClient(SUITE), ALIAS, [], poll_interval_s=0.01, echo=lines.append)
    responder.start()
    responder.stop()
    assert not responder.is_alive()
    assert responder.errors and "ConnectError" in responder.errors[0]
    assert len(lines) == 1  # the same error is printed once


@respx.mock
def test_suite_read_timeout_is_not_retried():
    # The suite may already be processing the request; a retry would be a second authorization request.
    respx.post(f"{VERIFY}/v2/vp-request").mock(
        return_value=httpx.Response(201, json={"transactionId": "tx", "requestId": "rq", "requestUri": "https://r"})
    )
    respx.get(AUTHZ).mock(side_effect=httpx.ReadTimeout("slow"))
    handoff = authorization_handoff()
    test = waiting(exposed={"authorization_endpoint": AUTHZ})
    record = handoff.deliver(test)
    assert record.http_status is None and record.error.startswith("ReadTimeout")
    assert not handoff.wants(test)


@respx.mock
def test_suite_connection_error_is_retried():
    respx.post(f"{VERIFY}/v2/vp-request").mock(
        return_value=httpx.Response(201, json={"transactionId": "tx", "requestId": "rq", "requestUri": "https://r"})
    )
    respx.get(AUTHZ).mock(side_effect=httpx.ConnectError("refused"))
    handoff = authorization_handoff()
    test = waiting(exposed={"authorization_endpoint": AUTHZ})
    handoff.deliver(test)
    assert handoff.wants(test)


# --------------------------------------------------------------------------------------------------------------
# Issuer tests: credential offer, then its transaction code
# --------------------------------------------------------------------------------------------------------------

CERTIFY = "https://certify.inji.test:18450"
CERTIFY_ALIAS = "inji-certify-20261004T193000Z-abc123"
OFFER_ENDPOINT = f"{SUITE}/test/a/{CERTIFY_ALIAS}/credential_offer"
# The suite shows the endpoint with an example value for the code.
TX_CODE_ENDPOINT = f"{SUITE}/test/a/{CERTIFY_ALIAS}/tx_code?code=your_tx_code"
CONFIG_ID = "InjiConformanceSdJwtVc"
CLAIMS = {"fullName": "Asha Test-Farmer", "dateOfBirth": "1990-01-15", "gender": "Female"}
ISSUER_MODULE = "oid4vci-1_0-issuer-happy-flow"


def offer_handoff(**options) -> CredentialOfferHandoff:
    return CredentialOfferHandoff(SuiteClient(SUITE), CertifyClient(CERTIFY), CONFIG_ID, CLAIMS, **options)


def waits_for_offer(test_id="t1") -> TestView:
    return TestView(test_id, ISSUER_MODULE, "WAITING", {"exposed": {"credential_offer_endpoint": OFFER_ENDPOINT}})


def waits_for_tx_code(test_id="t1") -> TestView:
    exposed = {"credential_offer_endpoint": OFFER_ENDPOINT, "tx_code_endpoint": TX_CODE_ENDPOINT}
    return TestView(test_id, ISSUER_MODULE, "WAITING", {"exposed": exposed})


def mock_certify_offers() -> respx.Route:
    """Inji Certify gives every request its own offer: .../credential-offer-data/offer-1, offer-2, ..."""
    numbers = itertools.count(1)

    def create(_request):
        uri = f"{CERTIFY}/v1/certify/credential-offer-data/offer-{next(numbers)}"
        url = "openid-credential-offer://?" + urllib.parse.urlencode({"credential_offer_uri": uri})
        return httpx.Response(200, json={"credential_offer_uri": url})

    return respx.post(f"{CERTIFY}/v1/certify/pre-authorized-data").mock(side_effect=create)


def sent_body(route: respx.Route, call: int = -1) -> dict:
    return json.loads(route.calls[call].request.content)


def query_of(route: respx.Route, call: int = -1) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(route.calls[call].request.url.query.decode())


@respx.mock
def test_offer_is_delivered_by_reference_then_its_transaction_code():
    certify_route = mock_certify_offers()
    offer_route = respx.get(OFFER_ENDPOINT).mock(return_value=httpx.Response(204))
    tx_route = respx.get(f"{SUITE}/test/a/{CERTIFY_ALIAS}/tx_code").mock(return_value=httpx.Response(204))
    handoff = offer_handoff()

    assert handoff.wants(waits_for_offer())
    offer_record = handoff.deliver(waits_for_offer())

    request = sent_body(certify_route)
    assert request["credential_configuration_id"] == CONFIG_ID
    assert request["claims"] == CLAIMS
    assert request["expires_in"] == 600
    assert len(request["tx_code"]) == 6 and request["tx_code"].isdigit()
    offer_uri = f"{CERTIFY}/v1/certify/credential-offer-data/offer-1"
    assert query_of(offer_route) == {"credential_offer_uri": [offer_uri]}
    assert (offer_record.kind, offer_record.http_status, offer_record.error) == (
        HandoffKind.CREDENTIAL_OFFER,
        204,
        None,
    )
    assert offer_record.data == {"offer_uri": offer_uri}
    assert offer_record.detail.startswith("offer 1: Inji Certify offer offer-1 (with tx_code) delivered by reference")
    # The transaction code never goes into the record: handoffs.jsonl stays in the report folder.
    assert request["tx_code"] not in json.dumps(offer_record.as_json())

    # The suite took the offer and now waits for the code the user would type.
    assert handoff.wants(waits_for_tx_code())
    tx_record = handoff.deliver(waits_for_tx_code())

    assert query_of(tx_route) == {"code": [request["tx_code"]]}  # replaces the example value in the endpoint
    assert (tx_record.kind, tx_record.http_status, tx_record.error) == (HandoffKind.TX_CODE, 204, None)
    assert request["tx_code"] not in json.dumps(tx_record.as_json())
    # One code per offer: the test still shows both endpoints while the suite redeems the code.
    assert not handoff.wants(waits_for_tx_code())
    assert certify_route.call_count == 1


@respx.mock
def test_test_that_waits_for_an_offer_again_gets_a_new_one():
    # The multiple-clients module runs the flow once per client; pre-authorized codes are single-use.
    certify_route = mock_certify_offers()
    offer_route = respx.get(OFFER_ENDPOINT).mock(return_value=httpx.Response(204))
    tx_route = respx.get(f"{SUITE}/test/a/{CERTIFY_ALIAS}/tx_code").mock(return_value=httpx.Response(204))
    handoff = offer_handoff()

    records = []
    for _client in range(2):
        records.append(handoff.deliver(waits_for_offer()))
        records.append(handoff.deliver(waits_for_tx_code()))
        assert handoff.wants(waits_for_offer())  # the suite removed tx_code_endpoint and waits for an offer

    assert [r.kind for r in records] == [HandoffKind.CREDENTIAL_OFFER, HandoffKind.TX_CODE] * 2
    assert [query_of(offer_route, n)["credential_offer_uri"][0].rsplit("/", 1)[1] for n in (0, 1)] == [
        "offer-1",
        "offer-2",
    ]
    assert records[2].detail.startswith("offer 2:") and "offer 2" in records[3].detail
    # Each code goes with its own offer.
    assert [query_of(tx_route, n)["code"][0] for n in (0, 1)] == [
        sent_body(certify_route, n)["tx_code"] for n in (0, 1)
    ]


@respx.mock
def test_a_test_gets_at_most_max_offers():
    certify_route = mock_certify_offers()
    respx.get(OFFER_ENDPOINT).mock(return_value=httpx.Response(204))
    handoff = offer_handoff()  # the default limit
    delivered = 0
    while handoff.wants(waits_for_offer()):
        handoff.deliver(waits_for_offer())
        delivered += 1
    assert delivered == certify_route.call_count == 6
    # The limit is per test: another test of the same run still gets its offer.
    assert handoff.wants(waits_for_offer("t2"))


@respx.mock
def test_offers_and_codes_are_kept_apart_per_test():
    certify_route = mock_certify_offers()
    respx.get(OFFER_ENDPOINT).mock(return_value=httpx.Response(204))
    tx_route = respx.get(f"{SUITE}/test/a/{CERTIFY_ALIAS}/tx_code").mock(return_value=httpx.Response(204))
    handoff = offer_handoff()
    handoff.deliver(waits_for_offer("t1"))
    handoff.deliver(waits_for_offer("t2"))
    handoff.deliver(waits_for_tx_code("t2"))
    assert query_of(tx_route)["code"] == [sent_body(certify_route, 1)["tx_code"]]
    assert handoff.wants(waits_for_tx_code("t1")) and not handoff.wants(waits_for_tx_code("t2"))


def test_offer_handoff_ignores_tests_that_do_not_wait_for_it():
    handoff = offer_handoff()
    assert not handoff.wants(TestView("t1", ISSUER_MODULE, "WAITING", {"exposed": {}}))
    exposed = {"exposed": {"credential_offer_endpoint": OFFER_ENDPOINT}}
    assert not handoff.wants(TestView("t1", ISSUER_MODULE, "CONFIGURED", exposed))
    assert not handoff.wants(TestView("t1", ISSUER_MODULE, "RUNNING", exposed))
    # A transaction code is only sent for an offer this handoff delivered.
    assert not handoff.wants(waits_for_tx_code())


@respx.mock
def test_certify_error_inside_http_200_is_recorded_and_counts_as_an_offer():
    respx.post(f"{CERTIFY}/v1/certify/pre-authorized-data").mock(
        return_value=httpx.Response(
            200, json={"response": None, "errors": [{"errorCode": "invalid_request", "errorMessage": "Unknown claims"}]}
        )
    )
    offer_route = respx.get(OFFER_ENDPOINT).mock(return_value=httpx.Response(204))
    handoff = offer_handoff(max_offers=2)
    records = []
    while handoff.wants(waits_for_offer()):
        records.append(handoff.deliver(waits_for_offer()))
    assert len(records) == 2 and not offer_route.called
    assert all(r.http_status is None and "invalid_request: Unknown claims" in r.error for r in records)
    assert records[0].detail == "offer 1: POST /v1/certify/pre-authorized-data to Inji Certify"
    assert not handoff.wants(waits_for_tx_code())


@respx.mock
def test_offer_the_suite_refuses_leaves_no_code_to_send():
    mock_certify_offers()
    respx.get(OFFER_ENDPOINT).mock(return_value=httpx.Response(400, text="no test is waiting for an offer"))
    handoff = offer_handoff()
    record = handoff.deliver(waits_for_offer())
    assert (record.http_status, record.error) == (400, "no test is waiting for an offer")
    assert not handoff.wants(waits_for_tx_code())
    assert handoff.wants(waits_for_offer())  # the next offer may be taken


@respx.mock
def test_offer_is_not_repeated_after_a_suite_read_timeout():
    # The suite may already hold the offer; a second one would reach a test that no longer waits for it.
    mock_certify_offers()
    respx.get(OFFER_ENDPOINT).mock(side_effect=httpx.ReadTimeout("slow"))
    handoff = offer_handoff()
    record = handoff.deliver(waits_for_offer())
    assert record.http_status is None and record.error.startswith("ReadTimeout")
    assert record.data == {"offer_uri": f"{CERTIFY}/v1/certify/credential-offer-data/offer-1"}
    assert not handoff.wants(waits_for_offer())


@respx.mock
def test_offer_is_repeated_after_a_suite_connection_error():
    mock_certify_offers()
    respx.get(OFFER_ENDPOINT).mock(side_effect=httpx.ConnectError("refused"))
    handoff = offer_handoff()
    handoff.deliver(waits_for_offer())
    assert handoff.wants(waits_for_offer())


@respx.mock
def test_offer_without_a_transaction_code():
    certify_route = mock_certify_offers()
    respx.get(OFFER_ENDPOINT).mock(return_value=httpx.Response(204))
    handoff = offer_handoff(tx_code_length=0)
    record = handoff.deliver(waits_for_offer())
    assert "tx_code" not in sent_body(certify_route)
    assert "(without tx_code)" in record.detail
    assert not handoff.wants(waits_for_tx_code())


@respx.mock
def test_failed_transaction_code_delivery_is_recorded():
    mock_certify_offers()
    respx.get(OFFER_ENDPOINT).mock(return_value=httpx.Response(204))
    respx.get(f"{SUITE}/test/a/{CERTIFY_ALIAS}/tx_code").mock(side_effect=httpx.ReadTimeout("slow"))
    handoff = offer_handoff()
    handoff.deliver(waits_for_offer())
    record = handoff.deliver(waits_for_tx_code())
    assert (record.kind, record.http_status) == (HandoffKind.TX_CODE, None)
    assert record.error.startswith("ReadTimeout")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://s/test/a/x/tx_code?code=your_tx_code", "https://s/test/a/x/tx_code?code=123456"),
        ("https://s/test/a/x/tx_code", "https://s/test/a/x/tx_code?code=123456"),
        ("https://s/test/a/x/tx_code?keep=1&code=old", "https://s/test/a/x/tx_code?keep=1&code=123456"),
    ],
)
def test_with_query_replaces_values_of_the_same_name(url, expected):
    assert _with_query(url, {"code": "123456"}) == expected


@respx.mock
def test_responder_delivers_offers_only_to_its_own_run(tmp_path):
    respx.get(f"{SUITE}/api/runner/running").mock(return_value=httpx.Response(200, json=["mine", "other"]))
    respx.get(f"{SUITE}/api/info/mine").mock(
        return_value=httpx.Response(200, json={"testName": ISSUER_MODULE, "alias": CERTIFY_ALIAS, "status": "WAITING"})
    )
    respx.get(f"{SUITE}/api/info/other").mock(
        return_value=httpx.Response(
            200, json={"testName": ISSUER_MODULE, "alias": "inji-certify-another-run", "status": "WAITING"}
        )
    )
    states = iter(
        [
            {"exposed": {"credential_offer_endpoint": OFFER_ENDPOINT}},
            {"exposed": {"credential_offer_endpoint": OFFER_ENDPOINT, "tx_code_endpoint": TX_CODE_ENDPOINT}},
            {"exposed": {"credential_offer_endpoint": OFFER_ENDPOINT, "tx_code_endpoint": TX_CODE_ENDPOINT}},
        ]
    )
    respx.get(f"{SUITE}/api/runner/mine").mock(side_effect=lambda _request: httpx.Response(200, json=next(states)))
    other_runner = respx.get(f"{SUITE}/api/runner/other").mock(
        return_value=httpx.Response(200, json={"exposed": {"credential_offer_endpoint": "https://other/offer"}})
    )
    certify_route = mock_certify_offers()
    respx.get(OFFER_ENDPOINT).mock(return_value=httpx.Response(204))
    respx.get(f"{SUITE}/test/a/{CERTIFY_ALIAS}/tx_code").mock(return_value=httpx.Response(204))
    lines: list[str] = []
    log = tmp_path / "handoffs.jsonl"
    responder = Responder(SuiteClient(SUITE), CERTIFY_ALIAS, [offer_handoff()], log_path=log, echo=lines.append)

    for _ in range(3):
        responder.poll_once()

    assert [(r.test_id, r.kind) for r in responder.records] == [
        ("mine", HandoffKind.CREDENTIAL_OFFER),
        ("mine", HandoffKind.TX_CODE),
    ]
    assert certify_route.call_count == 1 and not other_runner.called
    assert [json.loads(line)["kind"] for line in log.read_text().splitlines()] == ["credential_offer", "tx_code"]
    assert lines[0].startswith(f"handoff credential_offer {ISSUER_MODULE} (mine): HTTP 204")
    assert lines[1].startswith(f"handoff tx_code {ISSUER_MODULE} (mine): HTTP 204")
