"""The Inji Verify client and the SDK-identical query string (golden test against the SDK's own code)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
import respx

from inji_conformance.inji_verify import VerifyClient, VerifyError, authorization_query, form_urlencode

GOLDEN = Path(__file__).parent / "golden"
CASES = json.loads((GOLDEN / "sdk_query_cases.json").read_text(encoding="utf-8"))
EXPECTED = {item["name"]: item["query"] for item in json.loads((GOLDEN / "sdk_query.json").read_text("utf-8"))}
BASE = "https://verify.inji.test:18451/v1/verify"


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_query_string_matches_the_sdk_golden_output(case):
    # sdk_query.json was produced by golden/sdk_query.mjs, which runs the SDK's function with URLSearchParams.
    assert authorization_query(case["client_id"], case["response"]) == EXPECTED[case["name"]]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_golden_file_is_current_with_the_sdk_function():
    produced = subprocess.run(
        ["node", str(GOLDEN / "sdk_query.mjs")], capture_output=True, text=True, check=True, encoding="utf-8"
    ).stdout
    assert json.loads(produced) == json.loads((GOLDEN / "sdk_query.json").read_text("utf-8"))


def test_form_urlencode_follows_the_whatwg_serializer():
    # "~" is encoded and "*" is not, unlike urllib.parse.urlencode; spaces become "+".
    assert form_urlencode([("a b", "~*-._ +/é")]) == "a+b=%7E*-._+%2B%2F%C3%A9"


def test_by_reference_request_carries_only_client_id_and_request_uri():
    query = authorization_query("x509_san_dns:test.example.com", {"requestUri": "https://v/x", "requestId": "r"})
    assert query == "client_id=x509_san_dns%3Atest.example.com&request_uri=https%3A%2F%2Fv%2Fx"


@respx.mock
def test_create_vp_request_posts_the_sdk_body():
    route = respx.post(f"{BASE}/v2/vp-request").mock(
        return_value=httpx.Response(201, json={"transactionId": "t", "requestId": "r", "requestUri": "u"})
    )
    client = VerifyClient(BASE)
    body = client.create_vp_request("x509_san_dns:h", {"credentials": []}, "direct_post")
    sent = json.loads(route.calls.last.request.content)
    assert body["requestUri"] == "u"
    assert sent["clientId"] == "x509_san_dns:h"
    assert sent["dcqlQuery"] == {"credentials": []}
    assert sent["responseMode"] == "direct_post"
    assert len(sent["nonce"]) >= 16


@respx.mock
def test_create_vp_request_error_keeps_the_status():
    respx.post(f"{BASE}/v2/vp-request").mock(return_value=httpx.Response(400, json={"errorCode": "invalid"}))
    with pytest.raises(VerifyError) as caught:
        VerifyClient(BASE).create_vp_request("x", {}, None)
    assert caught.value.status == 400
    assert "HTTP 400" in str(caught.value)


@respx.mock
def test_vp_result_returns_none_when_missing():
    respx.get(f"{BASE}/vp-result/t1").mock(return_value=httpx.Response(200, json={"vpResultStatus": "SUCCESS"}))
    respx.get(f"{BASE}/vp-result/t2").mock(return_value=httpx.Response(404))
    client = VerifyClient(BASE)
    assert client.vp_result("t1") == {"vpResultStatus": "SUCCESS"}
    assert client.vp_result("t2") is None
