"""The verification evidence upload, the HTML export, the run manifest and the combined run."""

from __future__ import annotations

import argparse
import base64
import io
import json
import threading
import time
import zipfile
from pathlib import Path

import httpx
import pytest
import respx
from PIL import Image

from inji_conformance import manifest, model, run
from inji_conformance.collect import evidence_path, review_from_vp_result
from inji_conformance.handoff import HandoffRecord, TestView, VerificationEvidenceHandoff, render_evidence
from inji_conformance.inji_verify import VerifyClient
from inji_conformance.model import Component, ExitCode, HandoffKind, ReviewOutcome
from inji_conformance.suite import SuiteClient

SUITE = "https://localhost.emobix.co.uk:18443"
VERIFY = "https://verify.inji.test:18451/v1/verify"
VALID = {"transactionId": "tx1", "vpResultStatus": "SUCCESS", "vcResults": [{"verificationStatus": "VALID"}]}


def evidence_handoff(tmp_path: Path, transactions: dict[str, str]) -> VerificationEvidenceHandoff:
    return VerificationEvidenceHandoff(
        SuiteClient(SUITE),
        VerifyClient(VERIFY),
        transactions,
        tmp_path / "run" / "verify" / "evidence",
        lambda module: "valid",
        relative_to=tmp_path / "run",
        result_wait_s=0,
    )


def waiting_for_upload(test_id: str = "t1", required: int = 1) -> TestView:
    return TestView(test_id, "oid4vp-1final-verifier-happy-flow", "WAITING", {"browser": {"uploadsRequired": required}})


def test_evidence_is_wanted_only_for_a_waiting_upload_of_a_known_transaction(tmp_path):
    handoff = evidence_handoff(tmp_path, {"t1": "tx1"})
    assert handoff.wants(waiting_for_upload())
    assert not handoff.wants(waiting_for_upload(required=0))
    assert not handoff.wants(waiting_for_upload("t2"))
    finished = TestView("t1", "m", "FINISHED", {"browser": {"uploadsRequired": 1}})
    assert not handoff.wants(finished)


@respx.mock
def test_evidence_uploads_inji_verifys_verdict_into_every_open_placeholder(tmp_path):
    respx.get(f"{SUITE}/api/log/t1/images").mock(
        return_value=httpx.Response(200, json=[{"_id": "a", "upload": "P1"}, {"_id": "b", "img": "data:x"}])
    )
    respx.get(f"{VERIFY}/vp-result/tx1").mock(return_value=httpx.Response(200, json=VALID))
    upload = respx.post(f"{SUITE}/api/log/t1/images/P1").mock(return_value=httpx.Response(200, json={}))
    handoff = evidence_handoff(tmp_path, {"t1": "tx1"})

    record = handoff.deliver(waiting_for_upload())

    assert (record.kind, record.http_status, record.error) == (HandoffKind.VERIFICATION_EVIDENCE, 200, None)
    assert record.data["evidence"] == "verify/evidence/oid4vp-1final-verifier-happy-flow-t1.png"
    body = upload.calls.last.request.content.decode()
    assert upload.calls.last.request.headers["content-type"] == "text/plain"
    assert body.startswith("data:image/png;base64,")
    png = base64.b64decode(body.split(",", 1)[1])
    assert png == (tmp_path / "run" / record.data["evidence"]).read_bytes()
    assert Image.open(io.BytesIO(png)).format == "PNG"
    assert not handoff.wants(waiting_for_upload())  # done: one upload per test


@respx.mock
def test_evidence_without_a_verdict_is_a_failed_record_and_is_retried(tmp_path):
    respx.get(f"{SUITE}/api/log/t1/images").mock(return_value=httpx.Response(200, json=[{"upload": "P1"}]))
    respx.get(f"{VERIFY}/vp-result/tx1").mock(return_value=httpx.Response(404))
    handoff = evidence_handoff(tmp_path, {"t1": "tx1"})
    record = handoff.deliver(waiting_for_upload())
    assert record.http_status is None and "no verdict" in record.error
    assert handoff.wants(waiting_for_upload())


def test_rendered_evidence_is_a_png_of_the_verdict():
    png = render_evidence("m", "t1", "tx1", {"vpResultStatus": "FAILED", "vcResults": [{}]}, "invalid")
    image = Image.open(io.BytesIO(png))
    assert image.format == "PNG" and image.width == 1000
    assert image.getpixel((5, 5)) == (180, 35, 24)  # the red banner of a failed verification


def test_review_takes_the_evidence_of_the_last_successful_upload():
    records = [
        HandoffRecord("t1", "m", HandoffKind.VERIFICATION_EVIDENCE, "x", None, 1, error="e", data={"evidence": "a"}),
        HandoffRecord("t1", "m", HandoffKind.VERIFICATION_EVIDENCE, "x", 200, 1, data={"evidence": "b.png"}),
    ]
    assert evidence_path(records) == "b.png"
    assert evidence_path(records[:1]) is None
    review = review_from_vp_result("valid", VALID, evidence_path(records))
    assert review.confirmed and review.observed is ReviewOutcome.VALID


# --- HTML export ------------------------------------------------------------------------------------------------


@respx.mock
def test_html_export_is_extracted_and_mapped_to_test_ids(tmp_path, capsys):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("index.html", "<html/>")
        bundle.writestr("test-log-oid4vci-1_0-issuer-happy-flow-AbC123.html", "<html/>")
        bundle.writestr("../escape.html", "x")
    respx.get(f"{SUITE}/api/plan/exporthtml/P1").mock(
        return_value=httpx.Response(
            200, content=buffer.getvalue(), headers={"content-disposition": 'attachment; filename="plan-P1.zip"'}
        )
    )
    exports = tmp_path / "certify" / "exports"
    exports.mkdir(parents=True)
    pages = run.export_html(SuiteClient(SUITE), "P1", exports)
    assert pages == {"AbC123": "certify/exports/html/test-log-oid4vci-1_0-issuer-happy-flow-AbC123.html"}
    assert (exports / "plan-P1-html.zip").is_file()
    assert not (tmp_path / "certify" / "escape.html").exists()


@respx.mock
def test_failed_html_export_is_reported_not_fatal(tmp_path, capsys):
    respx.get(f"{SUITE}/api/plan/exporthtml/P1").mock(return_value=httpx.Response(500))
    assert run.export_html(SuiteClient(SUITE), "P1", tmp_path) == {}
    assert "HTML export of plan P1 failed" in capsys.readouterr().err


# --- manifest and combined runs ---------------------------------------------------------------------------------


def results_for(component: Component, started: str, finished: str, code: ExitCode = ExitCode.OK) -> model.Results:
    return model.Results(
        schema_version="1",
        run_id="20261014T000000Z-abc123",
        component=component,
        track=model.Track.GATE,
        gating=True,
        suite=model.SuiteInfo(base_url=SUITE, version="5.3.1"),
        target=model.TargetInfo(base_url="https://x.inji.test"),
        plan=model.PlanInfo(name=f"{component.value}-plan", variant={}),
        modules=(),
        summary=model.Summary.of(()),
        gate=model.Gate(passed=code == ExitCode.OK, exit_code=code),
        started_at=started,
        finished_at=finished,
    )


def test_manifest_needs_the_git_commit(monkeypatch, tmp_path):
    monkeypatch.delenv(manifest.ENV_GIT_COMMIT, raising=False)
    args = ("20261014T000000Z-abc123", model.RunMode.COMPONENT, model.Track.GATE, "2026-10-14T00:00:00Z")
    assert manifest.build(*args, "2026-10-14T00:01:00Z", [], parallel=None, out=tmp_path) is None


def test_manifest_records_commit_images_and_wall_times(monkeypatch, tmp_path):
    images = tmp_path / "images.json"
    images.write_text(
        json.dumps([{"service": "certify", "image": "inji/certify:1", "digest": "sha256:" + "a" * 64, "commit": ""}]),
        encoding="utf-8",
    )
    monkeypatch.setenv(manifest.ENV_GIT_COMMIT, "ABCDEF1")
    monkeypatch.setenv(manifest.ENV_GIT_DIRTY, "0")
    monkeypatch.setenv(manifest.ENV_IMAGES_FILE, str(images))
    monkeypatch.setenv(manifest.ENV_COMMAND, "./run-conformance.sh\n--combined\n")
    built = manifest.build(
        "20261014T000000Z-abc123",
        model.RunMode.COMBINED,
        model.Track.GATE,
        "2026-10-14T00:00:00Z",
        "2026-10-14T00:10:00Z",
        [
            (results_for(Component.CERTIFY, "2026-10-14T00:00:05Z", "2026-10-14T00:04:05Z"), 0),
            (results_for(Component.VERIFY, "2026-10-14T00:00:05Z", "2026-10-14T00:02:05Z", ExitCode.GATE_FAILED), 1),
        ],
        parallel=True,
        out=tmp_path,
    )
    path = manifest.write(built, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert model.validate(data, model.DocumentKind.RUN_MANIFEST) == []
    assert data["harness"] == {"git_commit": "abcdef1", "git_dirty": False, "runner_version": manifest.__version__}
    assert [c["wall_time_s"] for c in data["components"]] == [240.0, 120.0]
    assert data["gate"] == {"passed": False, "exit_code": 1}
    assert data["command"] == ["./run-conformance.sh", "--combined"]
    assert data["images"] == [{"service": "certify", "image": "inji/certify:1", "digest": "sha256:" + "a" * 64}]


def combined_args(tmp_path: Path, serial: bool) -> argparse.Namespace:
    return argparse.Namespace(
        combined=True, component=None, serial=serial, track="gate", out=tmp_path / "out", timeout_minutes=None
    )


@pytest.mark.parametrize("serial", [False, True])
def test_combined_runs_both_plans_and_returns_the_worst_exit_code(monkeypatch, tmp_path, serial):
    monkeypatch.setenv(manifest.ENV_GIT_COMMIT, "abcdef1")
    active, overlap = set(), []
    lock = threading.Lock()

    def fake_component(args, component, *, run_id, out, label):
        with lock:
            active.add(component)
            overlap.append(len(active))
        time.sleep(0.2)
        with lock:
            active.discard(component)
        code = ExitCode.GATE_FAILED if component is Component.VERIFY else ExitCode.OK
        return int(code), results_for(component, "2026-10-14T00:00:00Z", "2026-10-14T00:01:00Z", code)

    monkeypatch.setattr(run, "run_component", fake_component)
    assert run.cmd_run(combined_args(tmp_path, serial)) == ExitCode.GATE_FAILED
    assert (max(overlap) == 2) is (not serial)
    data = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert data["mode"] == "combined" and data["parallel"] is (not serial)
    assert [c["component"] for c in data["components"]] == ["certify", "verify"]


def test_combined_run_keeps_the_other_plan_when_one_crashes(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv(manifest.ENV_GIT_COMMIT, raising=False)

    def fake_component(args, component, *, run_id, out, label):
        if component is Component.CERTIFY:
            raise RuntimeError("boom")
        return 0, results_for(component, "2026-10-14T00:00:00Z", "2026-10-14T00:01:00Z")

    monkeypatch.setattr(run, "run_component", fake_component)
    assert run.cmd_run(combined_args(tmp_path, False)) == ExitCode.ENVIRONMENT_NOT_READY
    out = capsys.readouterr()
    assert "inji-conformance run (certify): RuntimeError: boom" in out.err
    assert "verify exit 0" in out.out
