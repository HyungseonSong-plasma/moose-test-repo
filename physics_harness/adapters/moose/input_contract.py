"""Canonical structural contracts for generated MOOSE inputs.

The contract is independent from emitted HIT text.  A case declares stable
semantic object IDs plus their required MOOSE realization shape; the adapter
then verifies both the in-memory IR and the rendered input.  This prevents a
syntactically valid input from silently losing a required object or parameter.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable

from .input import MooseInput, MooseInputError


class MooseInputContractError(ValueError):
    """Raised when generated MOOSE input violates its declared contract."""


@dataclass(frozen=True)
class MooseObjectContract:
    object_id: str
    path: str
    type_name: str | None
    parameters: tuple[str, ...] = ()


@dataclass(frozen=True)
class MooseAssignmentContract:
    path: str
    name: str


@dataclass(frozen=True)
class MooseInputContract:
    contract_id: str
    objects: tuple[MooseObjectContract, ...] = ()
    assignments: tuple[MooseAssignmentContract, ...] = ()


@dataclass(frozen=True)
class MooseInputAudit:
    status: str
    stage: str
    missing: tuple[str, ...] = ()
    unexpected: tuple[str, ...] = ()
    mutated: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_ASSIGNMENT_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>[^#\r\n]*?)"
    r"\s*(?:#.*)?$"
)
_BLOCK_RE = re.compile(r"^\s*\[([^\]]*)\]\s*(?:#.*)?$")


def _require_nonempty(value: str, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise MooseInputContractError(f"{field} must be non-empty")
    return text


def _validate_contract(contract: MooseInputContract) -> None:
    _require_nonempty(contract.contract_id, "contract_id")
    object_ids = [_require_nonempty(item.object_id, "object_id") for item in contract.objects]
    duplicate_ids = sorted(name for name, count in Counter(object_ids).items() if count > 1)
    if duplicate_ids:
        raise MooseInputContractError(
            "duplicate semantic object IDs: " + ", ".join(duplicate_ids)
        )

    paths = [_require_nonempty(item.path, f"{item.object_id}.path") for item in contract.objects]
    duplicate_paths = sorted(path for path, count in Counter(paths).items() if count > 1)
    if duplicate_paths:
        raise MooseInputContractError(
            "multiple semantic IDs claim the same MOOSE path: " + ", ".join(duplicate_paths)
        )

    assignment_keys = [(item.path, item.name) for item in contract.assignments]
    duplicate_assignments = sorted(
        f"{path or '<root>'}/{name}"
        for (path, name), count in Counter(assignment_keys).items()
        if count > 1
    )
    if duplicate_assignments:
        raise MooseInputContractError(
            "duplicate assignment contracts: " + ", ".join(duplicate_assignments)
        )


def audit_case_ir(case: Any) -> MooseInputAudit:
    """Compare target IR against its independently declared semantic contract."""
    contract = getattr(case, "input_contract", None)
    if contract is None:
        return MooseInputAudit(
            status="FAIL",
            stage="IR",
            missing=("input_contract",),
        )
    _validate_contract(contract)

    blocks = tuple(getattr(case, "blocks", ()))
    assignments = tuple(getattr(case, "assignments", ()))

    block_ids = [str(getattr(block, "object_id", "") or "").strip() for block in blocks]
    missing_identity = [
        str(getattr(block, "path", "<unknown>"))
        for block, object_id in zip(blocks, block_ids)
        if not object_id
    ]
    if missing_identity:
        return MooseInputAudit(
            status="FAIL",
            stage="IR",
            missing=tuple(f"semantic_id:{path}" for path in sorted(missing_identity)),
        )

    duplicate_ids = sorted(name for name, count in Counter(block_ids).items() if count > 1)
    actual_by_id = {object_id: block for object_id, block in zip(block_ids, blocks)}
    expected_by_id = {item.object_id: item for item in contract.objects}

    missing = sorted(set(expected_by_id) - set(actual_by_id))
    unexpected = sorted(set(actual_by_id) - set(expected_by_id))
    mutated: list[str] = []

    if duplicate_ids:
        mutated.extend(f"duplicate_id:{name}" for name in duplicate_ids)

    for object_id in sorted(set(expected_by_id).intersection(actual_by_id)):
        expected = expected_by_id[object_id]
        actual = actual_by_id[object_id]
        if actual.path != expected.path:
            mutated.append(
                f"{object_id}:path:{expected.path!r}->{actual.path!r}"
            )
        if actual.type_name != expected.type_name:
            mutated.append(
                f"{object_id}:type:{expected.type_name!r}->{actual.type_name!r}"
            )
        actual_parameters = tuple(sorted(name for name, _ in actual.parameters))
        expected_parameters = tuple(sorted(expected.parameters))
        if actual_parameters != expected_parameters:
            mutated.append(
                f"{object_id}:parameters:{expected_parameters!r}->{actual_parameters!r}"
            )

    expected_assignments = {(item.path, item.name) for item in contract.assignments}
    actual_assignments = {(item.path, item.name) for item in assignments}
    for path, name in sorted(expected_assignments - actual_assignments):
        missing.append(f"assignment:{path or '<root>'}/{name}")
    for path, name in sorted(actual_assignments - expected_assignments):
        unexpected.append(f"assignment:{path or '<root>'}/{name}")

    status = "PASS" if not (missing or unexpected or mutated) else "FAIL"
    return MooseInputAudit(
        status=status,
        stage="IR",
        missing=tuple(missing),
        unexpected=tuple(unexpected),
        mutated=tuple(mutated),
    )


def _prefix_paths(paths: Iterable[str]) -> set[str]:
    result: set[str] = set()
    for path in paths:
        parts = [part for part in path.split("/") if part]
        for end in range(1, len(parts) + 1):
            result.add("/".join(parts[:end]))
    return result


def _direct_parameters(text: str, path: str) -> dict[str, str]:
    doc = MooseInput(text)
    span = doc.unique(path)
    lines = text[span.start : span.end].splitlines()
    depth = 0
    result: dict[str, str] = {}

    for line in lines[1:-1]:
        block_match = _BLOCK_RE.match(line)
        if block_match:
            token = block_match.group(1).strip()
            if token in {"", "../"}:
                depth = max(0, depth - 1)
            else:
                depth += 1
            continue
        if depth:
            continue
        match = _ASSIGNMENT_RE.match(line)
        if not match:
            continue
        name = match.group("name")
        if name in result:
            raise MooseInputContractError(f"duplicate parameter {path}/{name}")
        result[name] = match.group("value").strip()
    return result


def _root_parameters(text: str) -> dict[str, str]:
    depth = 0
    result: dict[str, str] = {}
    for line in text.splitlines():
        block_match = _BLOCK_RE.match(line)
        if block_match:
            token = block_match.group(1).strip()
            if token in {"", "../"}:
                depth = max(0, depth - 1)
            else:
                depth += 1
            continue
        if depth:
            continue
        match = _ASSIGNMENT_RE.match(line)
        if not match:
            continue
        name = match.group("name")
        if name in result:
            raise MooseInputContractError(f"duplicate top-level parameter {name}")
        result[name] = match.group("value").strip()
    return result


def audit_generated_input(case: Any, text: str) -> MooseInputAudit:
    """Re-parse rendered HIT and compare it with the already-audited target IR."""
    ir_audit = audit_case_ir(case)
    if ir_audit.status != "PASS":
        return ir_audit

    try:
        doc = MooseInput(text)
    except MooseInputError as exc:
        return MooseInputAudit(
            status="FAIL",
            stage="REPARSE",
            mutated=(f"parse_error:{exc}",),
        )

    blocks = tuple(getattr(case, "blocks", ()))
    assignments = tuple(getattr(case, "assignments", ()))
    managed_paths = _prefix_paths(
        [block.path for block in blocks]
        + [item.path for item in assignments if item.path]
    )
    actual_paths = [block.path for block in doc.blocks]
    counts = Counter(actual_paths)

    missing = sorted(path for path in managed_paths if counts[path] == 0)
    unexpected = sorted(path for path in counts if path not in managed_paths)
    mutated: list[str] = [
        f"duplicate_path:{path}:{count}"
        for path, count in sorted(counts.items())
        if count > 1
    ]

    expected_by_path: dict[str, dict[str, str]] = {path: {} for path in managed_paths}
    expected_types: dict[str, str | None] = {path: None for path in managed_paths}
    semantic_id_by_path: dict[str, str] = {}

    for block in blocks:
        semantic_id_by_path[block.path] = block.object_id
        expected_types[block.path] = block.type_name
        expected_by_path[block.path].update(dict(block.parameters))
    for item in assignments:
        if item.path:
            expected_by_path.setdefault(item.path, {})[item.name] = item.value

    for path in sorted(managed_paths):
        if counts[path] != 1:
            continue
        try:
            actual_parameters = _direct_parameters(text, path)
        except (MooseInputError, MooseInputContractError) as exc:
            mutated.append(f"{path}:parameter_parse:{exc}")
            continue
        actual_type = actual_parameters.pop("type", None)
        expected_type = expected_types.get(path)
        identity = semantic_id_by_path.get(path, f"path:{path}")
        if actual_type != expected_type:
            mutated.append(
                f"{identity}:type:{expected_type!r}->{actual_type!r}"
            )
        expected_parameters = expected_by_path.get(path, {})
        if actual_parameters != expected_parameters:
            missing_names = sorted(set(expected_parameters) - set(actual_parameters))
            unexpected_names = sorted(set(actual_parameters) - set(expected_parameters))
            for name in missing_names:
                missing.append(f"{identity}:parameter:{name}")
            for name in unexpected_names:
                unexpected.append(f"{identity}:parameter:{name}")
            for name in sorted(set(expected_parameters).intersection(actual_parameters)):
                if expected_parameters[name] != actual_parameters[name]:
                    mutated.append(
                        f"{identity}:parameter:{name}:"
                        f"{expected_parameters[name]!r}->{actual_parameters[name]!r}"
                    )

    expected_root = {
        item.name: item.value for item in assignments if not item.path
    }
    try:
        actual_root = _root_parameters(text)
    except MooseInputContractError as exc:
        mutated.append(f"<root>:parameter_parse:{exc}")
        actual_root = {}

    for name in sorted(set(expected_root) - set(actual_root)):
        missing.append(f"assignment:<root>/{name}")
    for name in sorted(set(actual_root) - set(expected_root)):
        unexpected.append(f"assignment:<root>/{name}")
    for name in sorted(set(expected_root).intersection(actual_root)):
        if expected_root[name] != actual_root[name]:
            mutated.append(
                f"assignment:<root>/{name}:{expected_root[name]!r}->{actual_root[name]!r}"
            )

    status = "PASS" if not (missing or unexpected or mutated) else "FAIL"
    return MooseInputAudit(
        status=status,
        stage="REPARSE",
        missing=tuple(sorted(set(missing))),
        unexpected=tuple(sorted(set(unexpected))),
        mutated=tuple(sorted(set(mutated))),
    )


def require_case_ir_contract(case: Any) -> None:
    result = audit_case_ir(case)
    if result.status != "PASS":
        raise MooseInputContractError(f"IR input contract violation: {result.to_dict()}")


def require_generated_input_contract(case: Any, text: str) -> None:
    result = audit_generated_input(case, text)
    if result.status != "PASS":
        raise MooseInputContractError(
            f"generated input contract violation: {result.to_dict()}"
        )


def input_contract_manifest(case: Any) -> dict[str, Any]:
    contract = getattr(case, "input_contract", None)
    if contract is None:
        raise MooseInputContractError("case has no input contract")
    _validate_contract(contract)
    return {
        "schema_version": 1,
        "case_id": getattr(case, "case_id", None),
        "action_id": getattr(case, "action_id", None),
        "contract": asdict(contract),
        "ir_audit": audit_case_ir(case).to_dict(),
    }


def self_test() -> int:
    from .target import (
        MooseAssignment,
        MooseBlock,
        MooseCaseIR,
        emit_moose_input,
    )

    contract = MooseInputContract(
        contract_id="selftest.diffusion",
        objects=(
            MooseObjectContract(
                object_id="field.u",
                path="Variables/u",
                type_name="MooseVariableFVReal",
                parameters=("block",),
            ),
            MooseObjectContract(
                object_id="transport.u.diffusion",
                path="FVKernels/u_diffusion",
                type_name="FVDiffusion",
                parameters=("block", "coeff", "variable"),
            ),
        ),
        assignments=(
            MooseAssignmentContract(path="Executioner", name="num_steps"),
        ),
    )
    blocks = (
        MooseBlock(
            object_id="field.u",
            path="Variables/u",
            type_name="MooseVariableFVReal",
            parameters=(("block", "plasma"),),
        ),
        MooseBlock(
            object_id="transport.u.diffusion",
            path="FVKernels/u_diffusion",
            type_name="FVDiffusion",
            parameters=(
                ("variable", "u"),
                ("coeff", "D"),
                ("block", "plasma"),
            ),
        ),
    )
    case = MooseCaseIR(
        case_id="contract-selftest",
        action_id="contract-selftest",
        blocks=blocks,
        assignments=(MooseAssignment("Executioner", "num_steps", "1"),),
        input_contract=contract,
    )

    try:
        rendered = emit_moose_input(case)
        if audit_generated_input(case, rendered).status != "PASS":
            raise AssertionError("positive generated-input control failed")

        dropped = MooseCaseIR(
            case_id=case.case_id,
            action_id=case.action_id,
            blocks=blocks[:1],
            assignments=case.assignments,
            input_contract=contract,
        )
        if audit_case_ir(dropped).status != "FAIL":
            raise AssertionError("missing semantic object was not rejected")

        parameter_loss = MooseCaseIR(
            case_id=case.case_id,
            action_id=case.action_id,
            blocks=(
                blocks[0],
                MooseBlock(
                    object_id="transport.u.diffusion",
                    path="FVKernels/u_diffusion",
                    type_name="FVDiffusion",
                    parameters=(("variable", "u"), ("block", "plasma")),
                ),
            ),
            assignments=case.assignments,
            input_contract=contract,
        )
        if audit_case_ir(parameter_loss).status != "FAIL":
            raise AssertionError("required parameter loss was not rejected")

        emitted_loss = rendered.replace("    coeff = D\n", "", 1)
        if audit_generated_input(case, emitted_loss).status != "FAIL":
            raise AssertionError("rendered parameter loss was not rejected")

        unexpected = rendered.replace(
            "[FVKernels]\n",
            "[FVKernels]\n  [unexpected]\n    type = FVTimeKernel\n"
            "    variable = u\n  []\n",
            1,
        )
        result = audit_generated_input(case, unexpected)
        if result.status != "FAIL" or "FVKernels/unexpected" not in result.unexpected:
            raise AssertionError("unexpected generated object was not rejected")
    except Exception as exc:
        print(f"MOOSE_INPUT_CONTRACT_SELFTEST: FAIL ({exc})")
        return 1

    print("MOOSE_INPUT_CONTRACT_SELFTEST: PASS")
    return 0


__all__ = [
    "MooseAssignmentContract",
    "MooseInputAudit",
    "MooseInputContract",
    "MooseInputContractError",
    "MooseObjectContract",
    "audit_case_ir",
    "audit_generated_input",
    "input_contract_manifest",
    "require_case_ir_contract",
    "require_generated_input_contract",
    "self_test",
]
