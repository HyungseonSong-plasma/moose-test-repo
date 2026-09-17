"""Conservative static dependency-closure checks for MOOSE/HIT input.

Only local, typed provider-consumer relationships with unambiguous identifier
references are hard-failed here. Dynamic expressions and cross-MultiApp
references are deliberately deferred to real MOOSE parsing/runtime checks.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .input import BlockSpan, MooseInput

_TYPE_RE = re.compile(r"^\s*type\s*=\s*([^\s#]+)", re.MULTILINE)
_PARAM_RE_TEMPLATE = r"^\s*{name}\s*=\s*(?:'([^']*)'|\"([^\"]*)\"|([^#\n]+))"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class DependencyRule:
    object_type: str
    parameter: str
    provider_roots: tuple[str, ...]
    scope: str = "LOCAL"


@dataclass(frozen=True)
class DependencyFinding:
    code: str
    consumer: str
    object_type: str
    parameter: str
    reference: str
    provider_namespaces: tuple[str, ...]
    scope: str

    def format(self, source: str) -> str:
        providers = " | ".join(f"{root}/<name>" for root in self.provider_namespaces)
        return (
            f"{source}:{self.consumer}: {self.code}: {self.parameter}="
            f"{self.reference!r} has no local provider; expected {providers}"
        )


REFERENCE_RULES: tuple[DependencyRule, ...] = (
    DependencyRule("FunctionIC", "function", ("Functions",)),
    DependencyRule("VolumetricFlowRate", "vel_x", ("Variables", "AuxVariables")),
    DependencyRule("VolumetricFlowRate", "vel_y", ("Variables", "AuxVariables")),
    DependencyRule("VolumetricFlowRate", "vel_z", ("Variables", "AuxVariables")),
    DependencyRule("VolumetricFlowRate", "rhie_chow_user_object", ("UserObjects",)),
    DependencyRule("TimeIntegratedPostprocessor", "value", ("Postprocessors",)),
)


def _value_from_match(match: re.Match[str]) -> str:
    for group in match.groups():
        if group is not None:
            return group.strip()
    return ""


def _extract_param(block_text: str, name: str) -> str | None:
    pattern = re.compile(_PARAM_RE_TEMPLATE.format(name=re.escape(name)), re.MULTILINE)
    match = pattern.search(block_text)
    if not match:
        return None
    return _value_from_match(match)


def _direct_block_text(text: str, span: BlockSpan, blocks: list[BlockSpan]) -> str:
    """Return one block with direct child blocks removed from the inspected text."""
    depth = span.path.count("/")
    children = [
        child
        for child in blocks
        if child.start > span.start
        and child.end < span.end
        and child.path.startswith(span.path + "/")
        and child.path.count("/") == depth + 1
    ]
    result = text[span.start : span.end]
    for child in sorted(children, key=lambda item: item.start, reverse=True):
        start = child.start - span.start
        end = child.end - span.start
        result = result[:start] + result[end:]
    return result


def _simple_reference(value: str | None) -> str | None:
    """Return one plain local identifier; decline dynamic or compound references."""
    if value is None:
        return None
    tokens = value.split()
    if len(tokens) != 1:
        return None
    token = tokens[0].strip()
    return token if _IDENTIFIER_RE.fullmatch(token) else None


def validate_dependency_closure_text(
    text: str, source: str = "<memory>"
) -> list[DependencyFinding]:
    del source  # retained for symmetry with the other preflight validators
    doc = MooseInput(text)
    rules_by_type: dict[str, list[DependencyRule]] = {}
    for rule in REFERENCE_RULES:
        rules_by_type.setdefault(rule.object_type, []).append(rule)

    findings: list[DependencyFinding] = []
    for span in doc.blocks:
        direct_text = _direct_block_text(text, span, doc.blocks)
        type_match = _TYPE_RE.search(direct_text)
        if not type_match:
            continue
        object_type = type_match.group(1).strip()
        for rule in rules_by_type.get(object_type, []):
            reference = _simple_reference(_extract_param(direct_text, rule.parameter))
            if reference is None:
                continue
            if any(doc.find(f"{root}/{reference}") for root in rule.provider_roots):
                continue
            findings.append(
                DependencyFinding(
                    code="MISSING_PROVIDER",
                    consumer=span.path,
                    object_type=object_type,
                    parameter=rule.parameter,
                    reference=reference,
                    provider_namespaces=rule.provider_roots,
                    scope=rule.scope,
                )
            )
    return findings


def dependency_closure_self_test() -> int:
    safe = """
[Variables]
  [u]
  []
  [v]
  []
[]
[UserObjects]
  [rc]
    type = INSFVRhieChowInterpolator
  []
[]
[Functions]
  [ic_w_O_transient]
    type = ParsedFunction
    expression = '0.1'
  []
[]
[ICs]
  [ic_w_O]
    type = FunctionIC
    variable = w_O
    function = ic_w_O_transient
  []
[]
[Postprocessors]
  [power]
    type = ElementIntegralVariablePostprocessor
    variable = q
  []
  [energy]
    type = TimeIntegratedPostprocessor
    value = power
  []
  [flow]
    type = VolumetricFlowRate
    vel_x = u
    vel_y = v
    rhie_chow_user_object = rc
  []
[]
"""
    missing_function = safe.replace(
        "[Functions]\n  [ic_w_O_transient]\n    type = ParsedFunction\n    expression = '0.1'\n  []\n[]\n",
        "",
    )
    missing_velocity = safe.replace("  [u]\n  []\n", "")
    missing_rc = safe.replace(
        "[UserObjects]\n  [rc]\n    type = INSFVRhieChowInterpolator\n  []\n[]\n",
        "",
    )
    missing_pp = safe.replace(
        "  [power]\n    type = ElementIntegralVariablePostprocessor\n    variable = q\n  []\n",
        "",
    )
    dynamic_reference = safe.replace(
        "function = ic_w_O_transient", "function = ${selected_ic_function}"
    )

    checks = [
        ("safe local providers", not validate_dependency_closure_text(safe)),
        (
            "missing FunctionIC provider",
            [
                (f.consumer, f.parameter, f.reference)
                for f in validate_dependency_closure_text(missing_function)
            ]
            == [("ICs/ic_w_O", "function", "ic_w_O_transient")],
        ),
        (
            "missing velocity provider",
            any(
                f.consumer == "Postprocessors/flow"
                and f.parameter == "vel_x"
                and f.reference == "u"
                for f in validate_dependency_closure_text(missing_velocity)
            ),
        ),
        (
            "missing Rhie-Chow provider",
            any(
                f.consumer == "Postprocessors/flow"
                and f.parameter == "rhie_chow_user_object"
                and f.reference == "rc"
                for f in validate_dependency_closure_text(missing_rc)
            ),
        ),
        (
            "missing postprocessor provider",
            any(
                f.consumer == "Postprocessors/energy"
                and f.parameter == "value"
                and f.reference == "power"
                for f in validate_dependency_closure_text(missing_pp)
            ),
        ),
        (
            "dynamic reference deferred",
            not any(
                f.consumer == "ICs/ic_w_O"
                for f in validate_dependency_closure_text(dynamic_reference)
            ),
        ),
    ]
    failed = [name for name, ok in checks if not ok]
    if failed:
        print("DEPENDENCY_CLOSURE_PREFLIGHT_SELFTEST: FAIL")
        for name in failed:
            print("  -", name)
        return 1
    print("DEPENDENCY_CLOSURE_PREFLIGHT_SELFTEST: PASS")
    return 0
