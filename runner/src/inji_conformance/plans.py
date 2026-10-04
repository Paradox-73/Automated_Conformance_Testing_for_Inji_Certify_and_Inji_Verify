"""Plan templates (``conformance/plans/<component>.<plan>.json``) and their rendering into suite inputs.

A template names one suite test plan with its variant, the modules to run, the suite configuration and the data
the handoff responder needs. The file format is described in ``conformance/plans/README.md``. Rendering does two
things to the ``config`` block:

- ``${name}`` in any string is replaced by a run value (``run_id``, ``target_url``, ``suite_url``) or a template
  parameter. An unknown name is an error, so a typo never reaches the suite.
- ``{"$certs_keys": "<file>"}`` becomes the suite's own placeholder ``{<file>}`` written without quotes.
  ``run-test-plan.py`` replaces it with the content of ``certs-keys/<file>`` (a JWK, for example) before it creates
  the plan, so private keys never appear in the rendered file.

Keys named ``$comment`` are notes for people and are dropped from the rendered config.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from inji_conformance.model import Component, Track

_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
CERTS_KEYS_KEY = "$certs_keys"
COMMENT_KEY = "$comment"
# Characters run-test-plan.py's plan-spec grammar accepts in names and variant values (test_plan_parser.py).
_SPEC_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_SPEC_VALUE = re.compile(r"^[A-Za-z0-9_\-=,./ \\]+$")
# Marks a certs-keys reference in the JSON text so that render_config can unquote it; plain ASCII, so json.dumps
# leaves it unchanged.
_CERTS_KEYS_MARK = "@@inji-conformance-certs-keys@@"


class PlanError(ValueError):
    """A plan template is malformed or cannot be rendered."""


@dataclasses.dataclass(frozen=True)
class PlanTemplate:
    """One plan template file."""

    path: Path
    component: Component
    track: Track
    plan: str
    variant: Mapping[str, str]
    modules: tuple[str, ...]
    parameters: Mapping[str, str]
    certs_keys: Mapping[str, str]
    config: Mapping[str, Any]
    handoff: Mapping[str, Any]
    review: Mapping[str, Any]

    @property
    def name(self) -> str:
        """File name without ``.json``, for example ``verify.oid4vp-1final-verifier``."""
        return self.path.name.removesuffix(".json")

    def expected_review(self, module: str) -> str:
        """``valid`` or ``invalid``: the verdict Inji Verify must show for ``module`` when the suite asks for review."""
        if module in self.review.get("invalid", ()):
            return "invalid"
        return str(self.review.get("default", "valid"))


def load_template(path: str | Path) -> PlanTemplate:
    """Read and check a plan template. Raises PlanError naming the problem."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlanError(f"{path}: cannot read plan template: {error}") from error
    if not isinstance(data, dict):
        raise PlanError(f"{path}: a plan template is a JSON object")

    def need(key: str, kind: type) -> Any:
        if not isinstance(data.get(key), kind):
            raise PlanError(f"{path}: '{key}' is required and must be a {kind.__name__}")
        return data[key]

    try:
        component = Component(need("component", str))
        track = Track(data.get("track", Track.GATE.value))
    except ValueError as error:
        raise PlanError(f"{path}: {error}") from error
    plan = need("plan", str)
    variant = need("variant", dict)
    for name in (plan, *variant):
        if not _SPEC_NAME.match(name):
            raise PlanError(f"{path}: '{name}' is not a valid plan or variant name")
    for key, value in variant.items():
        if not isinstance(value, str) or not _SPEC_VALUE.match(value):
            raise PlanError(f"{path}: variant {key}={value!r} is not a valid variant value")
    modules = tuple(data.get("modules", ()))
    if not all(isinstance(m, str) and _SPEC_NAME.match(m) for m in modules):
        raise PlanError(f"{path}: 'modules' must be a list of module names")
    return PlanTemplate(
        path=path,
        component=component,
        track=track,
        plan=plan,
        variant=dict(variant),
        modules=modules,
        parameters={str(k): str(v) for k, v in data.get("parameters", {}).items()},
        certs_keys=dict(data.get("certs_keys", {})),
        config=need("config", dict),
        handoff=dict(data.get("handoff", {})),
        review=dict(data.get("review", {})),
    )


def find_template(plans_dir: Path, component: Component, track: Track = Track.GATE) -> PlanTemplate:
    """The one template in ``plans_dir`` for ``component`` and ``track``."""
    found = []
    for path in sorted(plans_dir.glob(f"{component.value}.*.json")):
        template = load_template(path)
        if template.component is component and template.track is track:
            found.append(template)
    if len(found) != 1:
        names = ", ".join(t.path.name for t in found) or "none"
        raise PlanError(f"expected one {track.value} plan template for {component.value} in {plans_dir}, found {names}")
    return found[0]


def substitute(value: Any, variables: Mapping[str, str]) -> Any:
    """``value`` with every ``${name}`` replaced, ``$comment`` keys dropped and certs-keys references marked."""
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in variables:
                raise PlanError(f"unknown variable ${{{name}}} (known: {', '.join(sorted(variables))})")
            return variables[name]

        return _VARIABLE.sub(replace, value)
    if isinstance(value, Mapping):
        if set(value) == {CERTS_KEYS_KEY}:
            file_name = value[CERTS_KEYS_KEY]
            if not isinstance(file_name, str) or not re.match(r"^[A-Za-z0-9._-]+$", file_name):
                raise PlanError(f"{CERTS_KEYS_KEY} needs a plain file name, not {file_name!r}")
            return _CERTS_KEYS_MARK + file_name
        return {key: substitute(item, variables) for key, item in value.items() if key != COMMENT_KEY}
    if isinstance(value, list):
        return [substitute(item, variables) for item in value]
    return value


def render_config(template: PlanTemplate, run_values: Mapping[str, str]) -> str:
    """The suite configuration as text for ``run-test-plan.py``.

    The result is JSON except for the unquoted ``{<file>}`` placeholders, the same form as the suite's own
    configuration files. Run values win over template parameters of the same name.
    """
    variables = {**template.parameters, **run_values}
    rendered = substitute(template.config, variables)
    text = json.dumps(rendered, indent=2, ensure_ascii=False)
    return re.sub(r'"' + re.escape(_CERTS_KEYS_MARK) + r'([A-Za-z0-9._-]+)"', r"{\1}", text) + "\n"


def render_handoff(template: PlanTemplate, run_values: Mapping[str, str]) -> dict[str, Any]:
    """The ``handoff`` block with variables replaced."""
    return substitute(template.handoff, {**template.parameters, **run_values})


def plan_spec(template: PlanTemplate, config_path: str, modules: Sequence[str] | None = None) -> list[str]:
    """Positional arguments for ``run-test-plan.py``: ``plan[variant=value]...[:module,...]`` and the config path.

    ``config_path`` must use only the characters the suite's plan-spec grammar allows in a path (letters, digits,
    ``-``, ``_``, ``.``, ``/``); pass a path relative to the working directory of the script.
    """
    if not re.match(r"^[A-Za-z0-9_./-]+$", config_path):
        raise PlanError(f"config path {config_path!r} has characters run-test-plan.py cannot parse")
    selected = list(modules) if modules else list(template.modules)
    for module in selected:
        if not _SPEC_NAME.match(module):
            raise PlanError(f"{module!r} is not a valid module name")
    spec = template.plan + "".join(f"[{key}={value}]" for key, value in template.variant.items())
    if selected:
        spec += ":" + ",".join(selected)
    return [spec, config_path]
