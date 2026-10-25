"""The report and diff subcommands through inji_conformance.cli: files written, exit codes, error messages."""

from __future__ import annotations

import json
import re

from inji_conformance import cli
from inji_conformance.model import ExitCode

# The content rules of "scripts/check.sh secrets" that can apply to report output.
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN[ A-Z0-9]*PRIVATE KEY( BLOCK)?-----"),
    re.compile(r'"d"\s*:\s*"[A-Za-z0-9_-]{16,}"'),
    re.compile(r"(AKIA|ASIA)[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36,}"),
)


def run(capsys, *argv):
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_report_with_compare_writes_every_file(capsys, run_a, run_b, tmp_path):
    out = tmp_path / "wp13"
    code, stdout, _ = run(capsys, "report", "--run", str(run_a), "--compare", str(run_b), "--out", str(out))
    assert code == ExitCode.OK
    assert sorted(path.name for path in out.iterdir()) == ["badge.svg", "diff.html", "summary.html", "summary.md"]
    assert "certify 10 ok, 1 gap | verify 10 ok, 1 gap" in stdout
    markdown = (out / "summary.md").read_text(encoding="utf-8")
    assert "| certify | 15 | 10 | 1 | 0 | 4 | 0 |" in markdown
    assert "0 new regressions, 2 fixed" in markdown
    assert markdown.startswith("### Inji conformance: gate passed with 1 workaround\n")
    assert (
        "- Workaround (certify): The TLS proxy added authorization_endpoint" in markdown
        and "`docs/findings/certify-as-metadata-authorization-endpoint.md`; "
        "turn it off with `CERTIFY_AS_METADATA=as-is`."
        in markdown
    )
    for path in out.iterdir():
        text = path.read_text(encoding="utf-8")
        assert "\r\n" not in text
        assert not any(pattern.search(text) for pattern in SECRET_PATTERNS), path.name


def test_report_is_idempotent(capsys, run_a, tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1791115200")
    out = tmp_path / "out"
    run(capsys, "report", "--run", str(run_a), "--out", str(out))
    first = {path.name: path.read_bytes() for path in out.iterdir()}
    run(capsys, "report", "--run", str(run_a), "--out", str(out))
    assert first == {path.name: path.read_bytes() for path in out.iterdir()}
    assert "diff.html" not in first


def test_combined_needs_both_components(capsys, run_a, tmp_path):
    code, _, err = run(capsys, "report", "--run", str(run_a / "verify"), "--combined", "--out", str(tmp_path))
    assert code == ExitCode.USAGE
    assert "--combined needs results of both certify and verify; found: verify" in err
    assert not (tmp_path / "summary.html").exists()


def test_combined_from_two_component_folders(capsys, run_a, tmp_path):
    code, _, _ = run(
        capsys,
        "report",
        "--run", str(run_a / "certify"),
        "--run", str(run_a / "verify"),
        "--combined",
        "--out", str(tmp_path),
    )  # fmt: skip
    assert code == ExitCode.OK
    page = (tmp_path / "summary.html").read_text(encoding="utf-8")
    assert "Combined run" in page and "Inji Certify (issuer)" in page and "Inji Verify (verifier)" in page


def test_report_on_a_missing_run(capsys, tmp_path):
    code, _, err = run(capsys, "report", "--run", str(tmp_path / "nope"), "--out", str(tmp_path / "out"))
    assert code == ExitCode.USAGE and "no such run folder" in err


def test_diff_exit_codes(capsys, run_a, run_b):
    assert run(capsys, "diff", str(run_a), str(run_a))[0] == ExitCode.OK
    code, stdout, _ = run(capsys, "diff", str(run_a), str(run_b))
    assert code == ExitCode.DIFF_CHANGED
    assert "oid4vci-1_0-issuer-happy-flow" in stdout and "NEW REGRESSION" in stdout
    assert run(capsys, "diff", "--strict", str(run_a), str(run_b))[0] == ExitCode.GATE_FAILED
    assert run(capsys, "diff", "--strict", str(run_b), str(run_a))[0] == ExitCode.OK


def test_diff_writes_html_and_json(capsys, run_a, run_b, tmp_path):
    code, _, _ = run(
        capsys, "diff", str(run_a), str(run_b), "--out", str(tmp_path), "--json", str(tmp_path / "diff.json")
    )
    assert code == ExitCode.DIFF_CHANGED
    assert "Run diff" in (tmp_path / "diff.html").read_text(encoding="utf-8")
    data = json.loads((tmp_path / "diff.json").read_text(encoding="utf-8"))
    assert data["counts"]["new_regressions"] == 2


def test_diff_on_an_invalid_run(capsys, run_a, tmp_path):
    (tmp_path / "results.json").write_text("{}", encoding="utf-8")
    code, _, err = run(capsys, "diff", str(run_a), str(tmp_path))
    assert code == ExitCode.USAGE and "is not valid as results" in err
