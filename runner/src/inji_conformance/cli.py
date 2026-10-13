"""The ``inji-conformance`` command.

Subcommands:

- ``run``       run a component's suite test plan against Inji Certify or Inji Verify and write results.json
- ``seed``      prepare a component for the suite (Inji Certify: the credential configuration the plan asks for)
- ``gate``      classify a run against the benchmark and exit with the gate's code
- ``report``    HTML summary and badge of one or more runs (``inji_conformance.report``)
- ``diff``      compare the verdicts of two runs (``inji_conformance.report``)
- ``validate``  check results, run manifest and benchmark files against the contract in conformance/schema/

Exit codes (``model.ExitCode``): 0 passed or valid, 1 gate failed or a file is invalid, 2 usage or configuration
error, 3 environment not ready, 4 whole-run timeout; ``diff`` exits 16 when the runs differ.

The ``report`` and ``diff`` subcommands live in the package ``inji_conformance.report`` so that it can change
without touching this file. That package provides:

- ``run_report(args: argparse.Namespace) -> int`` and ``run_diff(args: argparse.Namespace) -> int`` (required);
- ``add_report_arguments(parser)`` and ``add_diff_arguments(parser)`` (optional): when present they define the
  subcommands' arguments instead of the defaults below.

A report package that is missing or fails to import only disables ``report`` and ``diff``; every other subcommand
keeps working.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType

from inji_conformance import __version__, model
from inji_conformance.model import Component, DocumentKind, ExitCode, Track

REPORT_MODULE = "inji_conformance.report"

Handler = Callable[[argparse.Namespace], int]


def _run_handler(args: argparse.Namespace) -> int:
    # Imported here so that "validate" and "--help" work without the run's dependencies being importable.
    from inji_conformance.run import cmd_run

    return cmd_run(args)


def _gate_handler(args: argparse.Namespace) -> int:
    from inji_conformance.run import cmd_gate

    return cmd_gate(args)


def _seed_handler(args: argparse.Namespace) -> int:
    from inji_conformance.run import cmd_seed

    return cmd_seed(args)


# ---------------------------------------------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------------------------------------------


def _describe(kind: DocumentKind, data: object) -> str:
    """Short description of a valid document for the one-line result."""
    if kind is DocumentKind.RESULTS and isinstance(data, dict):
        return f"results v{data['schema_version']}, {data['component']}, {len(data['modules'])} modules"
    if kind is DocumentKind.RUN_MANIFEST and isinstance(data, dict):
        return f"run manifest v{data['schema_version']}, {len(data['components'])} components"
    count = len(data) if isinstance(data, list) else 0
    return f"{kind.value}, {_plural(count, 'entry', 'entries')}"


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else plural or singular + 's'}"


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate each file and print one line per file: ``validate <name>: valid (...)`` or ``... : invalid``."""
    try:
        schema_dir = model.require_schema_dir(args.schema_dir) if args.schema_dir else model.find_schema_dir()
    except model.SchemaNotFoundError as error:
        print(f"validate: {error}", file=sys.stderr)
        return ExitCode.USAGE

    worst = ExitCode.OK
    for path in args.files:
        name = Path(path).name
        try:
            data = model.read_json(path)
        except FileNotFoundError:
            print(f"validate {name}: no such file ({path})", file=sys.stderr)
            worst = max(worst, ExitCode.USAGE)
            continue
        except (OSError, UnicodeDecodeError) as error:
            print(f"validate {name}: cannot read: {error}", file=sys.stderr)
            worst = max(worst, ExitCode.USAGE)
            continue
        except json.JSONDecodeError as error:
            print(f"validate {name}: invalid (not JSON: {error})")
            worst = max(worst, ExitCode.GATE_FAILED)
            continue

        kind = DocumentKind(args.kind) if args.kind else model.detect_kind(path, data)
        if kind is None:
            print(f"validate {name}: cannot tell the kind of file; pass --kind", file=sys.stderr)
            worst = max(worst, ExitCode.USAGE)
            continue

        issues = model.validate(data, kind, schema_dir)
        if issues:
            print(f"validate {name}: invalid ({kind.value}, {_plural(len(issues), 'problem')})")
            for issue in issues:
                print(f"  {issue}")
            worst = max(worst, ExitCode.GATE_FAILED)
        elif not args.quiet:
            print(f"validate {name}: valid ({_describe(kind, data)})")
    return worst


# ---------------------------------------------------------------------------------------------------------------
# report and diff (implemented in inji_conformance.report)
# ---------------------------------------------------------------------------------------------------------------


def _load_report_module() -> tuple[ModuleType | None, str | None]:
    """The report package, or None with the reason it cannot be used."""
    try:
        return importlib.import_module(REPORT_MODULE), None
    except ModuleNotFoundError as error:
        if error.name and REPORT_MODULE.startswith(error.name):
            return None, f"{REPORT_MODULE} is not part of this installation"
        return None, f"cannot import {REPORT_MODULE}: {error}"
    except Exception as error:  # a broken report package must not take the other subcommands down with it
        return None, f"cannot import {REPORT_MODULE}: {type(error).__name__}: {error}"


def _default_report_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run", required=True, type=Path, metavar="DIR", help="run folder (holds manifest.json)")
    parser.add_argument("--combined", action="store_true", help="one report for both components of the run")
    parser.add_argument("--compare", type=Path, metavar="PREV", help="earlier run folder to compare against")
    parser.add_argument("--out", required=True, type=Path, metavar="DIR", help="folder for summary.html, badge.svg")


def _default_diff_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("before", type=Path, metavar="A", help="earlier run folder or results.json")
    parser.add_argument("after", type=Path, metavar="B", help="later run folder or results.json")
    parser.add_argument("--out", type=Path, metavar="DIR", help="also write diff.html into this folder")
    parser.add_argument("--strict", action="store_true", help="exit 1 when B has a regression A did not have")


def _report_handler(module: ModuleType | None, reason: str | None, function: str, command: str) -> Handler:
    def handler(args: argparse.Namespace) -> int:
        entry = getattr(module, function, None)
        if entry is None:
            why = reason or f"{REPORT_MODULE} has no {function}()"
            print(f"inji-conformance {command}: {why}", file=sys.stderr)
            return ExitCode.USAGE
        return int(entry(args))

    return handler


# ---------------------------------------------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------------------------------------------


def _modules_list(value: str) -> list[str]:
    modules = [item.strip() for item in value.split(",") if item.strip()]
    if not modules:
        raise argparse.ArgumentTypeError("expected one or more module names separated by commas")
    return modules


def build_parser() -> argparse.ArgumentParser:
    # argparse exits with 2 on a usage error, which is ExitCode.USAGE already.
    parser = argparse.ArgumentParser(
        prog="inji-conformance",
        description="OpenID conformance testing of Inji Certify and Inji Verify with the OpenID Foundation "
        "conformance suite.",
        epilog="Exit codes: 0 passed, 1 gate failed or invalid file, 2 usage or configuration error, "
        "3 environment not ready, 4 timeout; diff exits 16 when the runs differ.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    run = commands.add_parser("run", help="run a component's test plan and write results.json")
    which = run.add_mutually_exclusive_group(required=True)
    which.add_argument("--component", choices=[c.value for c in Component], help="component to test")
    which.add_argument("--combined", action="store_true", help="test both components in one run")
    run.add_argument("--target", metavar="URL", help="base URL of the system under test (default: the compose one)")
    run.add_argument("--modules", type=_modules_list, metavar="A,B", help="run only these test modules")
    run.add_argument(
        "--track",
        choices=[t.value for t in Track],
        default=Track.GATE.value,
        help="gate: the 1.0 Final plans (default); haip: the HAIP plans, never gating",
    )
    run.add_argument("--no-gate", action="store_true", help="write results without applying the benchmark gate")
    run.add_argument("--allow-stale", action="store_true", help="stale benchmark entries warn instead of failing")
    run.add_argument("--serial", action="store_true", help="with --combined: one plan after the other")
    run.add_argument("--no-seed", action="store_true", help="do not seed Inji Certify before the issuer plan")
    run.add_argument("--benchmark-dir", type=Path, metavar="DIR", help="default: conformance/benchmark")
    run.add_argument(
        "--template",
        metavar="NAME",
        help="plan template from conformance/plans to run instead of the default one, for example "
        "verify.oid4vp-1final-verifier-x509-san-dns",
    )
    run.add_argument(
        "--variant",
        action="append",
        metavar="NAME=VALUE",
        help="replace one variant value of the plan template, for example sender_constrain=mtls (repeatable)",
    )
    run.add_argument("--timeout-minutes", type=float, metavar="N", help="time limit for the whole run")
    run.add_argument("--out", type=Path, metavar="DIR", help="run folder to write into")
    run.set_defaults(handler=_run_handler)

    seed = commands.add_parser("seed", help="prepare a component for the suite (idempotent)")
    seed.add_argument("component", choices=[Component.CERTIFY.value])
    seed.add_argument("--target", metavar="URL", help="issuer URL of Inji Certify (default: the compose one)")
    seed.add_argument(
        "--track", choices=[t.value for t in Track], default=Track.GATE.value, help="plan template to seed for"
    )
    seed.set_defaults(handler=_seed_handler)

    gate = commands.add_parser("gate", help="apply the benchmark to a run and exit with the gate's code")
    gate.add_argument("--run", required=True, type=Path, metavar="DIR", help="component run folder")
    gate.add_argument("--benchmark-dir", type=Path, metavar="DIR", help="default: conformance/benchmark")
    gate.add_argument("--allow-stale", action="store_true", help="stale benchmark entries warn instead of failing")
    gate.add_argument("--junit", type=Path, metavar="FILE", help="also write JUnit XML for CI")
    gate.set_defaults(handler=_gate_handler)

    report_module, reason = _load_report_module()
    for name, help_text, function, defaults in (
        ("report", "HTML summary and badge of a run", "run_report", _default_report_arguments),
        ("diff", "compare the verdicts of two runs", "run_diff", _default_diff_arguments),
    ):
        sub = commands.add_parser(name, help=help_text)
        add_arguments = getattr(report_module, f"add_{name}_arguments", None) or defaults
        add_arguments(sub)
        sub.set_defaults(handler=_report_handler(report_module, reason, function, name))

    validate = commands.add_parser("validate", help="check files against the JSON Schemas and the contract rules")
    validate.add_argument("files", nargs="+", metavar="FILE", help="results, run manifest or benchmark JSON files")
    validate.add_argument(
        "--kind",
        choices=[k.value for k in DocumentKind],
        help="kind of every file (default: from the file name, then the content)",
    )
    validate.add_argument(
        "--schema-dir",
        type=Path,
        metavar="DIR",
        help=f"folder with the *.schema.json files (default: ${model.SCHEMA_DIR_ENV}, "
        "else conformance/schema in the checkout)",
    )
    validate.add_argument("-q", "--quiet", action="store_true", help="print only invalid files")
    validate.set_defaults(handler=cmd_validate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
