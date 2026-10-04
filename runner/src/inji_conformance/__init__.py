"""Automated OpenID conformance testing of Inji Certify and Inji Verify.

The package drives the OpenID Foundation conformance suite's own ``run-test-plan.py``, answers the steps where the
suite waits for the system under test, and writes one ``results.json`` per component. ``inji_conformance.model`` is
the typed form of that file, of the run manifest and of the benchmark files; ``inji_conformance.cli`` is the
``inji-conformance`` command.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("inji-conformance")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
