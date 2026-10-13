"""The handoff responder: does every step where a suite test waits for a person or for the system under test.

``run-test-plan.py`` creates each module and then only waits for it to finish. When a module needs something from
outside (Inji Verify's authorization request, a browser visit), the suite marks it WAITING and a person normally
acts in the suite's web page. The responder runs next to the script in a background thread and acts instead:

- polls ``GET /api/runner/running`` and keeps only the tests whose alias is this run's alias, so two runs against
  one suite never touch each other's tests;
- WAITING with an exposed ``authorization_endpoint`` (verifier tests): asks Inji Verify for an authorization
  request and sends its query string to that endpoint (``AuthorizationRequestHandoff``);
- WAITING with an exposed ``credential_offer_endpoint`` or ``tx_code_endpoint`` (issuer tests): asks Inji Certify for
  a pre-authorized offer, hands its URI to the suite's wallet, then sends the offer's transaction code
  (``CredentialOfferHandoff``);
- WAITING with a screenshot placeholder (``uploadsRequired``, verifier tests that end in REVIEW): reads Inji
  Verify's verdict for the test's transaction (``GET /vp-result/{transactionId}``), renders it to a PNG and uploads it
  into the placeholder (``VerificationEvidenceHandoff``);
- WAITING with front-channel URLs nobody visited: requests each URL and marks it visited;
- CONFIGURED for longer than a grace period: starts the test (the suite starts almost every test by itself, so
  this only fires for a test that waits for a manual start).

Every action becomes a ``HandoffRecord`` with its time, HTTP status and duration, written to ``handoffs.jsonl``
and printed as one progress line; the results builder copies them into ``results.json``.
"""

from __future__ import annotations

import dataclasses
import json
import threading
import time
import urllib.parse
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from inji_conformance.inji_certify import CertifyClient, CertifyError, new_tx_code
from inji_conformance.inji_verify import VerifyClient, VerifyError, authorization_query
from inji_conformance.model import HandoffKind
from inji_conformance.suite import SuiteClient


def utc_now() -> str:
    """Current UTC time in the results format, for example 2026-10-04T19:30:00Z."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclasses.dataclass
class HandoffRecord:
    """One handoff the responder performed (or tried to)."""

    test_id: str
    module: str
    kind: HandoffKind
    at: str
    http_status: int | None
    duration_ms: float
    detail: str = ""
    error: str | None = None
    # Data later steps need, for example Inji Verify's transaction id for reading its verdict. Not in results.json.
    data: dict[str, str] = dataclasses.field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        out = dataclasses.asdict(self)
        out["kind"] = self.kind.value
        return out


@dataclasses.dataclass(frozen=True)
class TestView:
    """What the responder knows about one running test when it decides on a handoff."""

    test_id: str
    module: str
    status: str
    runner: Mapping[str, Any]  # GET /api/runner/{id}: exposed values and browser state

    @property
    def exposed(self) -> Mapping[str, Any]:
        return self.runner.get("exposed") or {}

    @property
    def browser(self) -> Mapping[str, Any]:
        return self.runner.get("browser") or {}


class Handoff(Protocol):
    """A handoff kind. ``wants`` decides, ``deliver`` acts and returns the record."""

    def wants(self, test: TestView) -> bool: ...

    def deliver(self, test: TestView) -> HandoffRecord: ...


class AuthorizationRequestHandoff:
    """Verifier tests: deliver Inji Verify's authorization request to the suite's wallet.

    The suite exposes ``authorization_endpoint`` (``<suite>/test/a/<alias>/authorize``) and waits. This creates a
    request at Inji Verify, builds the SDK's query string and sends ``GET <authorization_endpoint>?<query>``.
    The suite then fetches ``request_uri`` from Inji Verify and posts the presentation to its ``response_uri``.
    Each test gets one request; a failed attempt is retried up to ``max_attempts`` times.
    """

    kind = HandoffKind.AUTHORIZATION_REQUEST

    def __init__(
        self,
        suite: SuiteClient,
        verify: VerifyClient,
        client_id: str,
        dcql_query: Mapping[str, Any],
        response_mode: str | None = None,
        max_attempts: int = 3,
    ):
        self.suite = suite
        self.verify = verify
        self.client_id = client_id
        self.dcql_query = dcql_query
        self.response_mode = response_mode
        self.max_attempts = max_attempts
        self._attempts: dict[str, int] = {}
        self._done: set[str] = set()
        self.transactions: dict[str, str] = {}  # test id -> Inji Verify transaction id of the delivered request

    def wants(self, test: TestView) -> bool:
        return (
            test.status == "WAITING"
            and bool(test.exposed.get("authorization_endpoint"))
            and test.test_id not in self._done
            and self._attempts.get(test.test_id, 0) < self.max_attempts
        )

    def deliver(self, test: TestView) -> HandoffRecord:
        self._attempts[test.test_id] = self._attempts.get(test.test_id, 0) + 1
        endpoint = str(test.exposed["authorization_endpoint"])
        at = utc_now()
        started = time.monotonic()
        try:
            request = self.verify.create_vp_request(self.client_id, self.dcql_query, self.response_mode)
        except (VerifyError, httpx.HTTPError) as error:
            return HandoffRecord(
                test.test_id,
                test.module,
                self.kind,
                at,
                None,
                _ms(started),
                detail="POST /v2/vp-request to Inji Verify",
                error=str(error),
            )
        query = authorization_query(self.client_id, request)
        separator = "&" if "?" in endpoint else "?"
        data = {
            "transaction_id": str(request.get("transactionId", "")),
            "request_id": str(request.get("requestId", "")),
        }
        sent = time.monotonic()
        try:
            response = self.suite.get(endpoint + separator + query)
        except httpx.HTTPError as error:
            if not isinstance(error, httpx.ConnectError):
                # The request may have reached the suite before the read failed. A second request would be a
                # second authorization request in the same test, so this test gets no retry.
                self._done.add(test.test_id)
            return HandoffRecord(
                test.test_id,
                test.module,
                self.kind,
                at,
                None,
                _ms(started),
                detail="GET authorization_endpoint",
                error=f"{type(error).__name__}: {error}",
                data=data,
            )
        self._done.add(test.test_id)
        if data["transaction_id"]:
            self.transactions[test.test_id] = data["transaction_id"]
        by = "request_uri" if request.get("requestUri") else "value"
        return HandoffRecord(
            test.test_id,
            test.module,
            self.kind,
            at,
            response.status_code,
            _ms(started),
            detail=f"Inji Verify request {data['request_id']} (by {by}) delivered to authorization_endpoint; "
            f"suite answered in {_ms(sent):.0f} ms",
            error=None if response.status_code < 400 else response.text[:300],
            data=data,
        )


class CredentialOfferHandoff:
    """Issuer tests: deliver a fresh Inji Certify offer, then its transaction code, each time a test waits for one.

    In the issuer-initiated pre-authorized code flow the suite exposes ``credential_offer_endpoint``
    (``<suite>/test/a/<alias>/credential_offer``) and waits. Without ``vci.static_tx_code`` in the configuration the
    suite then exposes ``tx_code_endpoint`` and waits again for the code the user would type into the wallet
    (``AbstractVCIIssuerTestModule.java`` at release-v5.3.1, ``handleCredentialOffer``). The handoff therefore:

    1. WAITING, ``credential_offer_endpoint`` exposed, no ``tx_code_endpoint``: ``POST /pre-authorized-data`` with
       the claims and a new random transaction code, then
       ``GET <credential_offer_endpoint>?credential_offer_uri=<uri>``;
    2. WAITING, ``tx_code_endpoint`` exposed, an offer of ours waiting for its code: ``GET <tx_code_endpoint>`` with
       ``code=<that code>``; the suite then redeems the code and requests the credential;
    3. a test that waits for an offer again (the multiple-clients module runs the flow once per client; the suite
       removes ``tx_code_endpoint`` while it waits for an offer) gets a new offer, because pre-authorized codes
       are single-use.

    The suite handles both requests synchronously, so when the GET returns the test is already in its next state.
    A test gets at most ``max_offers`` offers, so a test that keeps refusing them cannot loop forever.
    """

    def __init__(
        self,
        suite: SuiteClient,
        certify: CertifyClient,
        credential_configuration_id: str,
        claims: Mapping[str, Any],
        *,
        tx_code_length: int = 6,
        expires_in: int = 600,
        max_offers: int = 6,
    ):
        self.suite = suite
        self.certify = certify
        self.config_id = credential_configuration_id
        self.claims = dict(claims)
        self.tx_code_length = tx_code_length
        self.expires_in = expires_in
        self.max_offers = max_offers
        self._offers: dict[str, int] = {}  # test id -> offers delivered (or attempted)
        self._pending_tx_code: dict[str, str] = {}  # test id -> code of the offer the suite holds

    def _waits_for_tx_code(self, test: TestView) -> bool:
        return bool(test.exposed.get("tx_code_endpoint")) and test.test_id in self._pending_tx_code

    def _waits_for_offer(self, test: TestView) -> bool:
        return (
            bool(test.exposed.get("credential_offer_endpoint"))
            and not test.exposed.get("tx_code_endpoint")
            and self._offers.get(test.test_id, 0) < self.max_offers
        )

    def wants(self, test: TestView) -> bool:
        return test.status == "WAITING" and (self._waits_for_tx_code(test) or self._waits_for_offer(test))

    def deliver(self, test: TestView) -> HandoffRecord:
        if self._waits_for_tx_code(test):
            return self._deliver_tx_code(test)
        return self._deliver_offer(test)

    def _deliver_offer(self, test: TestView) -> HandoffRecord:
        number = self._offers.get(test.test_id, 0) + 1
        self._offers[test.test_id] = number
        self._pending_tx_code.pop(test.test_id, None)
        endpoint = str(test.exposed["credential_offer_endpoint"])
        at = utc_now()
        started = time.monotonic()

        def failed(detail: str, error: Exception, data: dict[str, str] | None = None) -> HandoffRecord:
            return HandoffRecord(
                test.test_id,
                test.module,
                HandoffKind.CREDENTIAL_OFFER,
                at,
                None,
                _ms(started),
                detail=f"offer {number}: {detail}",
                error=f"{type(error).__name__}: {error}",
                data=data or {},
            )

        tx_code = new_tx_code(self.tx_code_length) if self.tx_code_length else None
        try:
            offer = self.certify.create_offer(self.config_id, self.claims, tx_code=tx_code, expires_in=self.expires_in)
        except (CertifyError, httpx.HTTPError) as error:
            return failed("POST /v1/certify/pre-authorized-data to Inji Certify", error)
        sent = time.monotonic()
        try:
            response = self.suite.get(_with_query(endpoint, {"credential_offer_uri": offer.offer_uri}))
        except httpx.HTTPError as error:
            if not isinstance(error, httpx.ConnectError):
                # The suite may have taken the offer before the read failed. Another offer would reach a test that
                # no longer waits for one, so this test gets no further offer.
                self._offers[test.test_id] = self.max_offers
            return failed("GET credential_offer_endpoint", error, {"offer_uri": offer.offer_uri})
        if response.status_code < 400 and offer.tx_code:
            self._pending_tx_code[test.test_id] = offer.tx_code
        return HandoffRecord(
            test.test_id,
            test.module,
            HandoffKind.CREDENTIAL_OFFER,
            at,
            response.status_code,
            _ms(started),
            detail=f"offer {number}: Inji Certify offer {offer.offer_uri.rsplit('/', 1)[-1]} "
            f"({'with' if offer.tx_code else 'without'} tx_code) delivered by reference; "
            f"suite answered in {_ms(sent):.0f} ms",
            error=None if response.status_code < 400 else response.text[:300],
            data={"offer_uri": offer.offer_uri},
        )

    def _deliver_tx_code(self, test: TestView) -> HandoffRecord:
        code = self._pending_tx_code.pop(test.test_id)
        endpoint = str(test.exposed["tx_code_endpoint"])
        at = utc_now()
        started = time.monotonic()
        try:
            response = self.suite.get(_with_query(endpoint, {"code": code}))
            status, error = response.status_code, (None if response.status_code < 400 else response.text[:300])
        except httpx.HTTPError as exc:
            status, error = None, f"{type(exc).__name__}: {exc}"
        return HandoffRecord(
            test.test_id,
            test.module,
            HandoffKind.TX_CODE,
            at,
            status,
            _ms(started),
            detail=f"transaction code of offer {self._offers.get(test.test_id, 0)} delivered to tx_code_endpoint; "
            "the suite redeems the code and requests the credential within this call",
            error=error,
        )


class VerificationEvidenceHandoff:
    """Verifier tests that end in REVIEW: upload an image of Inji Verify's own verdict into the suite's placeholder.

    The suite cannot see the verifier's result screen, so after the presentation it asks for a screenshot and waits
    (``browser.uploadsRequired``). A person would upload a screenshot of Inji Verify's result page. The harness reads
    the same verdict from Inji Verify's API (``GET /vp-result/{transactionId}`` of the transaction the authorization
    request created), draws it as a PNG (``render_evidence``), keeps it in ``evidence/`` and uploads it with
    ``POST /api/log/{id}/images/{placeholder}``. The suite then finishes the module with result REVIEW, and the
    results builder compares the verdict with the one the module expects.
    """

    kind = HandoffKind.VERIFICATION_EVIDENCE

    def __init__(
        self,
        suite: SuiteClient,
        verify: VerifyClient,
        transactions: Mapping[str, str],
        evidence_dir: Path,
        expected: Callable[[str], str],
        *,
        relative_to: Path | None = None,
        max_attempts: int = 3,
        result_wait_s: float = 10.0,
    ):
        self.suite = suite
        self.verify = verify
        self.transactions = transactions
        self.evidence_dir = evidence_dir
        self.expected = expected
        self.relative_to = relative_to
        self.max_attempts = max_attempts
        self.result_wait_s = result_wait_s
        self._attempts: dict[str, int] = {}
        self._done: set[str] = set()

    def wants(self, test: TestView) -> bool:
        required = test.browser.get("uploadsRequired")
        return (
            test.status == "WAITING"
            and isinstance(required, int)
            and required > 0
            and test.test_id in self.transactions
            and test.test_id not in self._done
            and self._attempts.get(test.test_id, 0) < self.max_attempts
        )

    def _vp_result(self, transaction: str) -> Mapping[str, Any] | None:
        deadline = time.monotonic() + self.result_wait_s
        while True:
            result = self.verify.vp_result(transaction)
            if result or time.monotonic() >= deadline:
                return result
            time.sleep(1.0)

    def deliver(self, test: TestView) -> HandoffRecord:
        self._attempts[test.test_id] = self._attempts.get(test.test_id, 0) + 1
        transaction = self.transactions[test.test_id]
        at = utc_now()
        started = time.monotonic()

        def failed(detail: str, error: str) -> HandoffRecord:
            return HandoffRecord(
                test.test_id, test.module, self.kind, at, None, _ms(started), detail=detail, error=error
            )

        try:
            placeholders = [str(i["upload"]) for i in self.suite.images(test.test_id) if i.get("upload")]
            result = self._vp_result(transaction)
        except (VerifyError, httpx.HTTPError, ValueError) as error:
            return failed("reading the placeholder and Inji Verify's verdict", f"{type(error).__name__}: {error}")
        if not placeholders:
            return failed("GET /api/log/{id}/images", "the suite lists no open placeholder")
        if not result:
            return failed(f"GET /vp-result/{transaction}", "Inji Verify has no verdict for the transaction")
        png = render_evidence(test.module, test.test_id, transaction, result, self.expected(test.module))
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        path = self.evidence_dir / f"{test.module}-{test.test_id}.png"
        path.write_bytes(png)
        shown = path.relative_to(self.relative_to).as_posix() if self.relative_to else path.as_posix()
        statuses = []
        for placeholder in placeholders:
            try:
                statuses.append(self.suite.upload_image(test.test_id, placeholder, png).status_code)
            except httpx.HTTPError as error:
                return failed(f"POST /api/log/{{id}}/images/{placeholder}", f"{type(error).__name__}: {error}")
        status = max(statuses)
        if status < 400:
            self._done.add(test.test_id)
        return HandoffRecord(
            test.test_id,
            test.module,
            self.kind,
            at,
            status,
            _ms(started),
            detail=f"Inji Verify's verdict {result.get('vpResultStatus')} for {transaction} uploaded into "
            f"{len(placeholders)} placeholder(s) as {shown}",
            error=None if status < 400 else f"the suite answered HTTP {status}",
            data={
                "evidence": shown,
                "transaction_id": transaction,
                "vp_result_status": str(result.get("vpResultStatus", "")),
            },
        )


def render_evidence(module: str, test_id: str, transaction: str, result: Mapping[str, Any], expected: str) -> bytes:
    """A PNG that shows Inji Verify's verdict for one presentation, as its result page would."""
    import io

    from PIL import Image, ImageDraw, ImageFont

    status = str(result.get("vpResultStatus", "UNKNOWN"))
    credentials = [r for r in result.get("vcResults") or [] if isinstance(r, Mapping)]
    lines = [
        ("Presentation " + ("verified" if status == "SUCCESS" else "NOT verified") + f"  ({status})", 28),
        (f"Credentials: {len(credentials)}", 18),
        *[(f"  credential {n}: {r.get('verificationStatus', 'unknown')}", 18) for n, r in enumerate(credentials, 1)],
        ("", 10),
        (f"Inji Verify transaction {transaction}", 16),
        (f"Conformance suite module {module} ({test_id})", 16),
        (f"Verdict the module expects: {expected}", 16),
        ("", 10),
        (f"Drawn by inji-conformance at {utc_now()} from Inji Verify's GET /vp-result/{transaction}.", 14),
    ]

    def font(size: int) -> ImageFont.ImageFont:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:  # Pillow before 10.1 has one fixed-size default font
            return ImageFont.load_default()

    width, height = 1000, 70 + sum(size + 12 for _text, size in lines)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    banner = (22, 128, 61) if status == "SUCCESS" else (180, 35, 24)
    draw.rectangle([0, 0, width, 44], fill=banner)
    draw.text((20, 10), "Inji Verify - verification result", fill="white", font=font(20))
    y = 60
    for text, size in lines:
        draw.text((20, y), text, fill=(20, 20, 20), font=font(size))
        y += size + 12
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _with_query(url: str, params: Mapping[str, str]) -> str:
    """``url`` with ``params`` set in its query string, replacing values of the same name (such as the
    ``code=your_tx_code`` example value in the suite's ``tx_code_endpoint``)."""
    parts = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k not in params]
    query += list(params.items())
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


class BrowserVisitHandoff:
    """Front-channel URLs the suite wants a browser to open (``browser.urls`` not yet ``visited``)."""

    kind = HandoffKind.BROWSER_VISIT

    def __init__(self, suite: SuiteClient, http: httpx.Client | None = None):
        self.suite = suite
        self.http = http or httpx.Client(verify=False, timeout=30.0, follow_redirects=True)
        self._visited: set[tuple[str, str]] = set()

    def _pending(self, test: TestView) -> list[str]:
        visited = set(test.browser.get("visited") or [])
        return [
            url
            for url in test.browser.get("urls") or []
            if url not in visited and (test.test_id, url) not in self._visited
        ]

    def wants(self, test: TestView) -> bool:
        return test.status == "WAITING" and bool(self._pending(test))

    def deliver(self, test: TestView) -> HandoffRecord:
        url = self._pending(test)[0]
        self._visited.add((test.test_id, url))
        at = utc_now()
        started = time.monotonic()
        try:
            status = self.http.get(url).status_code
            error = None
        except httpx.HTTPError as exc:
            status, error = None, f"{type(exc).__name__}: {exc}"
        self.suite.mark_visited(test.test_id, url)
        return HandoffRecord(test.test_id, test.module, self.kind, at, status, _ms(started), detail=url, error=error)


class StartTestHandoff:
    """Starts a test that stayed CONFIGURED for ``grace_s`` seconds (the suite auto-starts all others)."""

    kind = HandoffKind.START_TEST

    def __init__(self, suite: SuiteClient, grace_s: float = 5.0, clock: Callable[[], float] = time.monotonic):
        self.suite = suite
        self.grace_s = grace_s
        self.clock = clock
        self._first_seen: dict[str, float] = {}
        self._started: set[str] = set()

    def wants(self, test: TestView) -> bool:
        if test.status != "CONFIGURED" or test.test_id in self._started:
            return False
        first = self._first_seen.setdefault(test.test_id, self.clock())
        return self.clock() - first >= self.grace_s

    def deliver(self, test: TestView) -> HandoffRecord:
        self._started.add(test.test_id)
        at = utc_now()
        started = time.monotonic()
        response = self.suite.start_test(test.test_id)
        return HandoffRecord(
            test.test_id,
            test.module,
            self.kind,
            at,
            response.status_code,
            _ms(started),
            detail="POST /api/runner/{id} for a test left in CONFIGURED",
        )


def _ms(since: float) -> float:
    return round((time.monotonic() - since) * 1000, 1)


class Responder(threading.Thread):
    """Background thread that watches this run's tests and performs their handoffs."""

    def __init__(
        self,
        suite: SuiteClient,
        alias: str,
        handoffs: list[Handoff],
        *,
        log_path: Path | None = None,
        poll_interval_s: float = 1.0,
        echo: Callable[[str], None] = print,
    ):
        super().__init__(name="handoff-responder", daemon=True)
        self.suite = suite
        self.alias = alias
        self.handoffs = handoffs
        self.log_path = log_path
        self.poll_interval_s = poll_interval_s
        self.echo = echo
        self.records: list[HandoffRecord] = []
        self.errors: list[str] = []
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._names: dict[str, str | None] = {}  # test id -> module name, None for another run's test

    def stop(self, timeout: float = 30.0) -> None:
        self._stop_event.set()
        if self.is_alive():
            self.join(timeout)

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception as error:  # keep watching: one failed poll must not end the run's handoffs
                # One line: an error can quote a whole HTML error page of the suite's proxy.
                message = " ".join(f"{type(error).__name__}: {error}".split())[:300]
                if not self.errors or self.errors[-1] != message:
                    self.echo(f"responder: poll failed: {message}")
                self.errors.append(message)
            self._stop_event.wait(self.poll_interval_s)

    def poll_once(self) -> None:
        """One pass over the running tests."""
        for test_id in self.suite.running_ids():
            if self._names.get(test_id, "") is None:
                continue  # another run's test
            info = self.suite.test_info(test_id)
            if info is None:
                continue
            if info.get("alias") != self.alias:
                self._names[test_id] = None
                continue
            module = str(info.get("testName", ""))
            self._names[test_id] = module
            status = str(info.get("status", ""))
            if status not in ("CONFIGURED", "WAITING"):
                continue
            runner = self.suite.runner_status(test_id) if status == "WAITING" else {}
            if runner is None:
                continue
            test = TestView(test_id, module, status, runner)
            for handoff in self.handoffs:
                if handoff.wants(test):
                    self._record(handoff.deliver(test))
                    break  # look again next pass: the test's state has changed

    def _record(self, record: HandoffRecord) -> None:
        with self._lock:
            self.records.append(record)
        status = record.http_status if record.http_status is not None else "no response"
        outcome = f"HTTP {status}" + (f", error: {record.error[:160]}" if record.error else "")
        self.echo(
            f"handoff {record.kind.value} {record.module} ({record.test_id}): {outcome} in {record.duration_ms:.0f} ms"
        )
        if self.log_path:
            with self.log_path.open("a", encoding="utf-8", newline="\n") as log:
                log.write(json.dumps(record.as_json(), ensure_ascii=False) + "\n")

    def records_for(self, test_id: str) -> list[HandoffRecord]:
        with self._lock:
            return [record for record in self.records if record.test_id == test_id]
