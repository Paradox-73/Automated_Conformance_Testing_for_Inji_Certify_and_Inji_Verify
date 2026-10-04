"""The handoff responder against a fake suite and a mocked Inji Verify."""

from __future__ import annotations

import json
import urllib.parse

import httpx
import respx

from inji_conformance.handoff import (
    AuthorizationRequestHandoff,
    BrowserVisitHandoff,
    Responder,
    StartTestHandoff,
    TestView,
)
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
