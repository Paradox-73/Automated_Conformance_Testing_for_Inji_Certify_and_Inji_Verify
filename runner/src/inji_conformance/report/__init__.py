"""Consolidated HTML report, status badge and run diff (the ``report`` and ``diff`` subcommands).

Modules:

- ``runs``: loads run folders and results files, validated against the contract in ``conformance/schema/``;
- ``html``: renders ``summary.html`` and ``diff.html`` from the Jinja2 templates in ``templates/`` with the style
  sheet and script in ``assets/`` inlined;
- ``badge``: renders ``badge.svg``;
- ``diff``: compares two runs module by module;
- ``redact``: removes private keys and credentials from free text before it reaches a page;
- ``commands``: the two subcommands, registered by ``inji_conformance.cli`` through the functions below.

The page layout follows ``docs/design/report-wireframe.svg``.
"""

from inji_conformance.report.commands import add_diff_arguments, add_report_arguments, run_diff, run_report

__all__ = ["add_diff_arguments", "add_report_arguments", "run_diff", "run_report"]
