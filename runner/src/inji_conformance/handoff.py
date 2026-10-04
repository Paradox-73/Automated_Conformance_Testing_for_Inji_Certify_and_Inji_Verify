"""The handoff responder: does every step where a suite test waits for a person or for the system under test.

``run-test-plan.py`` creates each module and then only waits for it to finish. When a module needs something from
outside (Inji Verify's authorization request, a browser visit), the suite marks it WAITING and a person normally
acts in the suite's web page. The responder runs next to the script in a background thread and acts instead:

- polls ``GET /api/runner/running`` and keeps only the tests whose alias is this run's alias, so two runs against
  one suite never touch each other's tests;
- WAITING with an exposed ``authorization_endpoint`` (verifier tests): asks Inji Verify for an authorization
  request and sends its query string to that endpoint (``AuthorizationRequestHandoff``);
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
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

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
                message = f"{type(error).__name__}: {error}"
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
