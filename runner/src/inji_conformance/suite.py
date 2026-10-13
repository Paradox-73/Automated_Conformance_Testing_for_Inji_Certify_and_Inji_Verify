"""The parts of the conformance suite's REST API the harness calls itself.

``run-test-plan.py`` creates, runs and exports the plan; this client is for what that script does not do: watching
this run's modules, answering their handoffs and reading results. The suite runs with its ``dev`` profile in the
harness, so no API token is sent. The suite's TLS certificate is its own self-signed one, so certificate checks are
off for it (as in ``run-test-plan.py`` in dev mode).

Endpoints (suite source ``TestRunner.java``, ``TestInfoApi.java``, ``LogApi.java``, ``TestPlanApi.java``):

- ``GET /api/server``: version;
- ``GET /api/runner/running``: ids of the tests the server holds in memory;
- ``GET /api/runner/{id}``: exposed values and browser state of a running test (404 once it is gone);
- ``POST /api/runner/{id}``: start a test left in CONFIGURED;
- ``POST /api/runner/browser/{id}/visit?url=``: mark a front-channel URL as visited;
- ``GET /api/info/{id}``: name, alias, plan id, status, result;
- ``GET /api/log/{id}``: log entries;
- ``GET /api/plan/{id}``: plan with its modules and their test ids;
- ``GET /api/plan/exporthtml/{id}``: the plan's results as a zip of HTML pages (what ``conformance.py exporthtml``
  downloads; ``run-test-plan.py --export-dir`` saves only the JSON export).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx


class SuiteError(RuntimeError):
    """A suite API call failed."""


class SuiteClient:
    def __init__(self, base_url: str, *, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(verify=False, timeout=timeout)  # the suite's own self-signed certificate

    def close(self) -> None:
        self._http.close()

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _get_json(self, path: str, *, missing_ok: bool = False) -> Any:
        response = self._http.get(self._url(path))
        if missing_ok and response.status_code == 404:
            return None
        if response.status_code != 200:
            raise SuiteError(f"GET {path} returned HTTP {response.status_code}: {response.text[:200]}")
        return response.json()

    # ---- reads -------------------------------------------------------------------------------------------------

    def server_info(self) -> dict[str, Any]:
        return self._get_json("api/server")

    def running_ids(self) -> list[str]:
        return list(self._get_json("api/runner/running") or [])

    def runner_status(self, test_id: str) -> dict[str, Any] | None:
        """Exposed values and browser state; None when the test is no longer held by the server."""
        return self._get_json(f"api/runner/{test_id}", missing_ok=True)

    def test_info(self, test_id: str) -> dict[str, Any] | None:
        return self._get_json(f"api/info/{test_id}", missing_ok=True)

    def test_log(self, test_id: str) -> list[dict[str, Any]]:
        return list(self._get_json(f"api/log/{test_id}") or [])

    def plan(self, plan_id: str) -> dict[str, Any] | None:
        return self._get_json(f"api/plan/{plan_id}", missing_ok=True)

    def export_html(self, plan_id: str) -> tuple[str, bytes]:
        """The plan's HTML export: (file name the suite gives it, zip bytes)."""
        response = self._http.get(self._url(f"api/plan/exporthtml/{plan_id}"), timeout=300.0)
        if response.status_code != 200:
            raise SuiteError(f"GET api/plan/exporthtml/{plan_id} returned HTTP {response.status_code}")
        disposition = response.headers.get("content-disposition", "")
        name = disposition.split('filename="', 1)[1].split('"', 1)[0] if 'filename="' in disposition else ""
        return (Path(name).name or f"{plan_id}-html.zip"), response.content

    def log_url(self, test_id: str) -> str:
        """Link to the live log page of a test."""
        return self._url(f"log-detail.html?log={test_id}")

    # ---- actions -----------------------------------------------------------------------------------------------

    def start_test(self, test_id: str) -> httpx.Response:
        return self._http.post(self._url(f"api/runner/{test_id}"))

    def mark_visited(self, test_id: str, url: str) -> httpx.Response:
        return self._http.post(self._url(f"api/runner/browser/{test_id}/visit"), params={"url": url})

    def get(self, url: str, *, timeout: float = 120.0) -> httpx.Response:
        """GET an absolute URL on the suite without following redirects (a front-channel request)."""
        return self._http.get(url, follow_redirects=False, timeout=timeout)
