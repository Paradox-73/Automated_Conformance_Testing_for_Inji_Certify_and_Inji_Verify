"""The inji-conformance command: validate output and exit codes, registered subcommands, report hook."""

from __future__ import annotations

import argparse
import json
import types

import httpx
import pytest
import respx

from inji_conformance import __version__, cli
from inji_conformance import run as run_module
from inji_conformance.model import ExitCode

SUITE = "https://localhost.emobix.co.uk:18443"
CERTIFY = "https://certify.inji.test:18450"
CERTIFY_CONFIGURATION = f"{CERTIFY}/v1/certify/credential-configurations/InjiConformanceSdJwtVc"


def run(capsys, *argv):
    code = cli.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


# --------------------------------------------------------------------------------------------------------------
# validate
# --------------------------------------------------------------------------------------------------------------


def test_validate_valid_file_prints_one_line(capsys, examples_dir):
    code, out, _ = run(capsys, "validate", str(examples_dir / "results-verify.example.json"))
    assert code == ExitCode.OK
    assert out == "validate results-verify.example.json: valid (results v1, verify, 11 modules)\n"


def test_validate_several_files(capsys, examples_dir):
    names = ["results-certify.example.json", "run-manifest.example.json", "certify.expected-skips.example.json"]
    code, out, _ = run(capsys, "validate", *(str(examples_dir / n) for n in names))
    assert code == ExitCode.OK
    assert out.splitlines() == [
        "validate results-certify.example.json: valid (results v1, certify, 15 modules)",
        "validate run-manifest.example.json: valid (run manifest v1, 2 components)",
        "validate certify.expected-skips.example.json: valid (expected-skips, 4 entries)",
    ]


def test_validate_invalid_file_lists_problems_and_exits_1(capsys, examples_dir):
    code, out, _ = run(capsys, "validate", str(examples_dir / "results-summary-mismatch.invalid.json"))
    assert code == ExitCode.GATE_FAILED
    lines = out.splitlines()
    assert lines[0] == "validate results-summary-mismatch.invalid.json: invalid (results, 2 problems)"
    assert lines[1:] == [
        "  $.summary.conforms: is 10, the modules give 9",
        "  $.summary.regression: is 0, the modules give 1",
    ]


def test_validate_reports_every_file_even_after_a_failure(capsys, examples_dir):
    code, out, _ = run(
        capsys,
        "validate",
        str(examples_dir / "results-unknown-verdict.invalid.json"),
        str(examples_dir / "results-verify.example.json"),
    )
    assert code == ExitCode.GATE_FAILED
    assert "validate results-verify.example.json: valid" in out


def test_validate_quiet_prints_only_invalid_files(capsys, examples_dir):
    code, out, _ = run(capsys, "validate", "--quiet", str(examples_dir / "results-verify.example.json"))
    assert (code, out) == (ExitCode.OK, "")


def test_validate_kind_option_overrides_the_file_name(capsys, examples_dir):
    code, out, _ = run(capsys, "validate", "--kind", "run-manifest", str(examples_dir / "results-verify.example.json"))
    assert code == ExitCode.GATE_FAILED
    assert "invalid (run-manifest" in out


def test_validate_missing_file_is_a_usage_error(capsys, tmp_path):
    code, _, err = run(capsys, "validate", str(tmp_path / "nope.json"))
    assert code == ExitCode.USAGE
    assert "no such file" in err


def test_validate_rejects_text_that_is_not_json(capsys, tmp_path):
    path = tmp_path / "results.json"
    path.write_text("{not json", encoding="utf-8")
    code, out, _ = run(capsys, "validate", str(path))
    assert code == ExitCode.GATE_FAILED
    assert out.startswith("validate results.json: invalid (not JSON")


def test_validate_unknown_kind_asks_for_kind(capsys, tmp_path):
    path = tmp_path / "data.json"
    path.write_text("[]", encoding="utf-8")
    code, _, err = run(capsys, "validate", str(path))
    assert code == ExitCode.USAGE
    assert "--kind" in err


def test_validate_with_a_schema_folder_that_lacks_schemas(capsys, tmp_path, examples_dir):
    code, _, err = run(
        capsys, "validate", "--schema-dir", str(tmp_path), str(examples_dir / "results-verify.example.json")
    )
    assert code == ExitCode.USAGE
    assert "results.schema.json" in err


def test_validate_with_an_explicit_schema_folder(capsys, schema_dir, examples_dir):
    code, _, _ = run(
        capsys, "validate", "--schema-dir", str(schema_dir), str(examples_dir / "results-verify.example.json")
    )
    assert code == ExitCode.OK


def test_validate_benchmark_written_by_hand(capsys, tmp_path):
    entry = {
        "test-name": "oid4vp-1final-verifier-*",
        "variant": "*",
        "configuration-filename": "*verify*.json",
        "comment": "The test set-up has no public DNS name for the verifier.",
        "owner": "environment",
        "spec": "OID4VP-1FINAL-5.9.3",
        "issue": "docs/findings/dns.md",
    }
    path = tmp_path / "verify.expected-skips.json"
    path.write_text(json.dumps([entry]), encoding="utf-8")
    code, out, _ = run(capsys, "validate", str(path))
    assert (code, out) == (ExitCode.OK, "validate verify.expected-skips.json: valid (expected-skips, 1 entry)\n")


# --------------------------------------------------------------------------------------------------------------
# Registered subcommands
# --------------------------------------------------------------------------------------------------------------


def _subcommands(parser: argparse.ArgumentParser) -> set[str]:
    (action,) = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    return set(action.choices)


def test_all_subcommands_are_registered():
    assert _subcommands(cli.build_parser()) == {"run", "seed", "gate", "report", "diff", "validate"}


def test_version(capsys):
    with pytest.raises(SystemExit) as caught:
        cli.main(["--version"])
    assert caught.value.code == 0
    assert capsys.readouterr().out.strip() == f"inji-conformance {__version__}"


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["run"],
        ["run", "--component", "certify", "--combined"],
        ["run", "--component", "wallet"],
        ["run", "--component", "verify", "--modules", ","],
        ["seed", "verify"],
        ["run", "--component", "verify", "--run-id", "not-a-run-id"],
        ["gate"],
        ["validate"],
    ],
)
def test_usage_errors_exit_2(capsys, argv):
    with pytest.raises(SystemExit) as caught:
        cli.main(argv)
    assert caught.value.code == ExitCode.USAGE
    capsys.readouterr()


def test_gate_reports_a_missing_run_folder(capsys):
    code, _, err = run(capsys, "gate", "--run", "x", "--allow-stale", "--junit", "j.xml")
    assert code == ExitCode.USAGE
    assert "inji-conformance gate: no results file at" in err


@respx.mock
def test_combined_haip_run_without_a_stack_names_each_component(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(run_module, "READY_TIMEOUT_S", 0)
    respx.get(f"{SUITE}/api/server").mock(side_effect=httpx.ConnectError("refused"))
    argv = ["run", "--combined", "--track", "haip", "--serial", "--allow-stale", "--out", str(tmp_path / "out")]
    code, out, err = run(capsys, *argv)
    assert code == ExitCode.ENVIRONMENT_NOT_READY
    assert "inji-conformance run (certify): the conformance suite" in err
    assert "inji-conformance run (verify): the conformance suite" in err
    assert (
        "certify plan oid4vci-1_0-issuer-haip-test-plan" in out
        and "verify plan oid4vp-1final-verifier-haip-test-plan" in out
    )


@respx.mock
def test_seed_certify_creates_the_configuration_once(capsys):
    respx.get(f"{CERTIFY}/.well-known/openid-credential-issuer").mock(
        return_value=httpx.Response(200, json={"credential_issuer": CERTIFY})
    )
    stored: dict = {}

    def read(_request):
        if stored:
            return httpx.Response(200, json={"credentialConfigKeyId": stored["credentialConfigKeyId"]})
        return httpx.Response(404, json={"response": None, "errors": [{"errorCode": "invalid_request"}]})

    def add(request):
        stored.update(json.loads(request.content))
        return httpx.Response(201, json={"id": stored["credentialConfigKeyId"], "status": "active"})

    respx.get(CERTIFY_CONFIGURATION).mock(side_effect=read)
    add_route = respx.post(f"{CERTIFY}/v1/certify/credential-configurations").mock(side_effect=add)

    first = run(capsys, "seed", "certify")
    second = run(capsys, "seed", "certify")

    assert first[:2] == (ExitCode.OK, "seed certify: credential configuration InjiConformanceSdJwtVc created\n")
    assert second[:2] == (
        ExitCode.OK,
        "seed certify: credential configuration InjiConformanceSdJwtVc already present\n",
    )
    assert add_route.call_count == 1
    # What reached Inji Certify is the rendered seed block: no template variables, no notes.
    assert stored["credentialConfigKeyId"] == "InjiConformanceSdJwtVc" and "$comment" not in stored


@respx.mock
def test_seed_certify_reports_an_error_inside_http_200(capsys):
    respx.get(f"{CERTIFY}/.well-known/openid-credential-issuer").mock(
        return_value=httpx.Response(200, json={"credential_issuer": CERTIFY})
    )
    respx.get(CERTIFY_CONFIGURATION).mock(return_value=httpx.Response(404, json={"errors": [{"errorCode": "x"}]}))
    respx.post(f"{CERTIFY}/v1/certify/credential-configurations").mock(
        return_value=httpx.Response(
            200, json={"response": None, "errors": [{"errorCode": "unsupported_format", "errorMessage": "no"}]}
        )
    )
    code, out, err = run(capsys, "seed", "certify")
    assert (code, out) == (ExitCode.ENVIRONMENT_NOT_READY, "")
    assert "inji-conformance seed: seeding Inji Certify failed" in err and "unsupported_format: no" in err


@respx.mock
def test_seed_certify_without_a_stack_exits_3(capsys, monkeypatch):
    monkeypatch.setattr(run_module, "READY_TIMEOUT_S", 0)
    respx.get(f"{CERTIFY}/.well-known/openid-credential-issuer").mock(side_effect=httpx.ConnectError("refused"))
    code, _, err = run(capsys, "seed", "certify")
    assert code == ExitCode.ENVIRONMENT_NOT_READY
    assert f"inji-conformance seed: Inji Certify at {CERTIFY} is not ready" in err


@respx.mock
def test_seed_takes_the_issuer_from_target_or_the_environment(capsys, monkeypatch):
    monkeypatch.setattr(run_module, "READY_TIMEOUT_S", 0)
    monkeypatch.setenv("HARNESS_CERTIFY_URL", "https://from-env.example/")
    respx.get("https://from-env.example/.well-known/openid-credential-issuer").mock(return_value=httpx.Response(503))
    respx.get("https://from-option.example/.well-known/openid-credential-issuer").mock(return_value=httpx.Response(503))
    assert "Inji Certify at https://from-env.example is not ready" in run(capsys, "seed", "certify")[2]
    err = run(capsys, "seed", "certify", "--target", "https://from-option.example")[2]
    assert "Inji Certify at https://from-option.example is not ready" in err and "HTTP 503" in err


@respx.mock
@pytest.mark.parametrize("with_out", [True, False])
def test_run_certify_without_a_stack_exits_3_and_writes_only_into_the_run_folder(
    capsys, monkeypatch, tmp_path, with_out
):
    monkeypatch.setattr(run_module, "READY_TIMEOUT_S", 0)
    monkeypatch.chdir(tmp_path)
    respx.get(f"{SUITE}/api/server").mock(side_effect=httpx.ConnectError("refused"))
    argv = ["run", "--component", "certify", "--no-gate"]
    if with_out:
        argv += ["--out", str(tmp_path / "out")]

    code, out, err = run(capsys, *argv)

    assert code == ExitCode.ENVIRONMENT_NOT_READY
    assert f"inji-conformance run: the conformance suite at {SUITE} is not ready" in err
    assert "certify plan oid4vci-1_0-issuer-test-plan [fapi_profile=vci, " in out
    assert f"against {CERTIFY}" in out
    # Without --out the run folder is $HARNESS_RUN_DIR/reports/<run id>, which the tests point at tmp_path.
    folders = sorted(str(p.relative_to(tmp_path).parent.as_posix()) for p in tmp_path.rglob("certify"))
    if with_out:
        assert folders == ["out"]
    else:
        (folder,) = folders
        assert folder.startswith("harness-run/reports/")


def test_run_certify_rejects_a_malformed_variant_option(capsys, tmp_path):
    code, _, err = run(
        capsys, "run", "--component", "certify", "--variant", "sender_constrain", "--out", str(tmp_path / "out")
    )
    assert code == ExitCode.USAGE
    assert "inji-conformance run: --variant expects NAME=VALUE, not 'sender_constrain'" in err
    assert not (tmp_path / "out").exists()


def test_run_parses_the_documented_options():
    args = cli.build_parser().parse_args(
        ["run", "--component", "verify", "--modules", "a, b", "--target", "https://verify.inji.test:18451"]
    )
    assert (args.component, args.modules, args.track, args.no_gate) == ("verify", ["a", "b"], "gate", False)
    assert (args.variant, args.no_seed) == (None, False)


def test_run_parses_the_issuer_options():
    args = cli.build_parser().parse_args(
        [
            "run",
            "--component",
            "certify",
            "--no-seed",
            "--variant",
            "sender_constrain=mtls",
            "--variant",
            "client_auth_type=client_attestation",
        ]
    )
    assert args.no_seed is True
    assert args.variant == ["sender_constrain=mtls", "client_auth_type=client_attestation"]


# --------------------------------------------------------------------------------------------------------------
# report and diff come from inji_conformance.report
# --------------------------------------------------------------------------------------------------------------


def test_report_and_diff_without_a_report_package(capsys, monkeypatch):
    monkeypatch.setattr(cli, "_load_report_module", lambda: (None, "inji_conformance.report is not installed"))
    code, _, err = run(capsys, "report", "--run", "a", "--out", "b")
    assert code == ExitCode.USAGE
    assert "inji-conformance report: inji_conformance.report is not installed" in err
    code, _, err = run(capsys, "diff", "a", "b")
    assert code == ExitCode.USAGE


def test_report_package_defines_arguments_and_handles_the_commands(capsys, monkeypatch):
    calls = []

    def add_diff_arguments(parser):
        parser.add_argument("left")
        parser.add_argument("right")
        parser.add_argument("--format", default="html")

    fake = types.SimpleNamespace(
        run_report=lambda args: calls.append(("report", args.run.name, args.combined)) or 0,
        run_diff=lambda args: calls.append(("diff", args.left, args.format)) or ExitCode.DIFF_CHANGED,
        add_diff_arguments=add_diff_arguments,
    )
    monkeypatch.setattr(cli, "_load_report_module", lambda: (fake, None))
    assert run(capsys, "report", "--run", "runs/a", "--combined", "--out", "o")[0] == 0
    assert run(capsys, "diff", "a", "b", "--format", "md")[0] == ExitCode.DIFF_CHANGED
    assert calls == [("report", "a", True), ("diff", "a", "md")]


def test_broken_report_package_leaves_validate_working(capsys, monkeypatch, examples_dir):
    real_import = cli.importlib.import_module

    def failing_import(name, *args):
        if name == cli.REPORT_MODULE:
            raise RuntimeError("template folder missing")
        return real_import(name, *args)

    monkeypatch.setattr(cli.importlib, "import_module", failing_import)
    code, _, _ = run(capsys, "validate", str(examples_dir / "results-verify.example.json"))
    assert code == ExitCode.OK
    code, _, err = run(capsys, "report", "--run", "a", "--out", "b")
    assert code == ExitCode.USAGE
    assert "RuntimeError: template folder missing" in err


def test_missing_report_package_is_reported_as_not_installed(monkeypatch):
    def missing(name, *args):
        raise ModuleNotFoundError(f"No module named {name!r}", name=name)

    monkeypatch.setattr(cli.importlib, "import_module", missing)
    module, reason = cli._load_report_module()
    assert module is None and "not part of this installation" in reason


def test_report_package_missing_a_dependency_names_it(monkeypatch):
    def missing_dependency(name, *args):
        raise ModuleNotFoundError("No module named 'jinja2'", name="jinja2")

    monkeypatch.setattr(cli.importlib, "import_module", missing_dependency)
    module, reason = cli._load_report_module()
    assert module is None and "jinja2" in reason
