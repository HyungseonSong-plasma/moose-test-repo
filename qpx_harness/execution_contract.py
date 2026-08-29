"""Machine-readable CORE-16 scientific execution contract.

This module turns the repository's intent-preserving scientific-execution ontology
into a small declarative contract that can be validated and evaluated without
embedding physics-specific thresholds in the validator itself.

Ontology chain:
    CLAIM -> MODEL -> NUMERICAL REGIME -> FRAMEWORK-EFFECTIVE CONFIGURATION
          -> RUNTIME REGIME / TRAJECTORY -> OBSERVATION / EVIDENCE -> DECISION

The contract owns conformance mechanics only. Physical/model thresholds remain
owned by the source/model/coupling contract (for example PS-23 / a scale audit).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
PHASES = ("P1", "P3", "DECISION")
OPS = {
    "eq",
    "ne",
    "lt",
    "le",
    "gt",
    "ge",
    "finite",
    "nonempty",
    "in",
    "not_in",
}
SEVERITIES = {"hard", "hold", "warn"}
DECISIONS = {"PENDING", "PASS", "FAIL", "HOLD", "REROUTE"}


class ExecutionContractError(ValueError):
    """Raised when a machine-readable execution contract is malformed."""


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExecutionContractError(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ExecutionContractError(f"{path} must be an array")
    return value


def _string(mapping: dict[str, Any], key: str, path: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ExecutionContractError(f"{path}.{key} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, path: str) -> list[str]:
    items = _list(value, path)
    if not all(isinstance(item, str) and item.strip() for item in items):
        raise ExecutionContractError(f"{path} must contain only non-empty strings")
    return [str(item).strip() for item in items]


def _lookup(root: dict[str, Any], dotted: str) -> Any:
    current: Any = root
    for token in dotted.split("."):
        if not token:
            raise KeyError(dotted)
        if isinstance(current, dict) and token in current:
            current = current[token]
            continue
        if isinstance(current, list):
            try:
                current = current[int(token)]
                continue
            except (ValueError, IndexError):
                pass
        raise KeyError(dotted)
    return current


def _operand_value(root: dict[str, Any], operand: dict[str, Any], path: str) -> Any:
    has_path = "path" in operand
    has_value = "value" in operand
    if has_path == has_value:
        raise ExecutionContractError(
            f"{path} must contain exactly one of 'path' or 'value'"
        )
    if has_path:
        ref = operand["path"]
        if not isinstance(ref, str) or not ref.strip():
            raise ExecutionContractError(f"{path}.path must be a non-empty string")
        return _lookup(root, ref.strip())
    return operand["value"]


def _numeric(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"expected numeric value, got {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise TypeError("expected finite numeric value")
    return result


def _evaluate_operator(op: str, left: Any, right: Any | None) -> bool:
    if op == "finite":
        try:
            if isinstance(left, list):
                return bool(left) and all(math.isfinite(_numeric(item)) for item in left)
            return math.isfinite(_numeric(left))
        except TypeError:
            return False
    if op == "nonempty":
        try:
            return len(left) > 0
        except TypeError:
            return bool(left)
    if op == "in":
        try:
            return left in right
        except TypeError:
            return False
    if op == "not_in":
        try:
            return left not in right
        except TypeError:
            return False
    if op == "eq":
        return left == right
    if op == "ne":
        return left != right

    try:
        lhs = _numeric(left)
        rhs = _numeric(right)
    except TypeError:
        return False
    if op == "lt":
        return lhs < rhs
    if op == "le":
        return lhs <= rhs
    if op == "gt":
        return lhs > rhs
    if op == "ge":
        return lhs >= rhs
    raise ExecutionContractError(f"unsupported operator: {op}")


def _validate_check(check: Any, index: int) -> dict[str, Any]:
    path = f"contract.checks[{index}]"
    item = _mapping(check, path)
    _string(item, "id", path)
    _string(item, "meaning", path)
    phase = _string(item, "phase", path)
    if phase not in PHASES:
        raise ExecutionContractError(f"{path}.phase must be one of {PHASES}")
    op = _string(item, "op", path)
    if op not in OPS:
        raise ExecutionContractError(f"{path}.op must be one of {sorted(OPS)}")
    severity = str(item.get("severity", "hard"))
    if severity not in SEVERITIES:
        raise ExecutionContractError(
            f"{path}.severity must be one of {sorted(SEVERITIES)}"
        )
    _mapping(item.get("left"), f"{path}.left")
    if op not in {"finite", "nonempty"}:
        _mapping(item.get("right"), f"{path}.right")
    elif "right" in item:
        raise ExecutionContractError(f"{path}.right is not used by operator {op}")
    on_fail = item.get("on_fail")
    if on_fail is not None and (not isinstance(on_fail, str) or not on_fail.strip()):
        raise ExecutionContractError(f"{path}.on_fail must be a non-empty string")
    return item


def validate_contract(data: dict[str, Any]) -> dict[str, Any]:
    """Validate ontology structure without requiring every runtime fact to exist yet."""
    root = _mapping(data, "contract")
    if root.get("schema_version") != SCHEMA_VERSION:
        raise ExecutionContractError(
            f"contract.schema_version must be {SCHEMA_VERSION}"
        )
    _string(root, "contract_id", "contract")

    claim = _mapping(root.get("claim"), "contract.claim")
    _string(claim, "statement", "contract.claim")
    _string(claim, "acceptance", "contract.claim")

    model = _mapping(root.get("model"), "contract.model")
    _string(model, "representation", "contract.model")
    _string_list(model.get("retained", []), "contract.model.retained")
    _string_list(model.get("reduced", []), "contract.model.reduced")
    _string_list(model.get("assumptions", []), "contract.model.assumptions")

    numerical = _mapping(root.get("numerical_regime"), "contract.numerical_regime")
    _string(numerical, "intent", "contract.numerical_regime")
    _mapping(numerical.get("declared_controls", {}), "contract.numerical_regime.declared_controls")
    _mapping(numerical.get("declared_scales", {}), "contract.numerical_regime.declared_scales")

    framework = _mapping(
        root.get("framework_effective"), "contract.framework_effective"
    )
    _string(framework, "provenance", "contract.framework_effective")
    _mapping(framework.get("controls", {}), "contract.framework_effective.controls")

    runtime = _mapping(root.get("runtime_regime"), "contract.runtime_regime")
    _mapping(runtime.get("observed", {}), "contract.runtime_regime.observed")

    evidence = _mapping(root.get("evidence"), "contract.evidence")
    requirements = _string_list(
        evidence.get("requirements", []), "contract.evidence.requirements"
    )
    if not requirements:
        raise ExecutionContractError(
            "contract.evidence.requirements must contain at least one requirement"
        )
    _mapping(evidence.get("observed", {}), "contract.evidence.observed")

    decision = _mapping(root.get("decision"), "contract.decision")
    status = _string(decision, "status", "contract.decision")
    if status not in DECISIONS:
        raise ExecutionContractError(
            f"contract.decision.status must be one of {sorted(DECISIONS)}"
        )

    checks = _list(root.get("checks"), "contract.checks")
    if not checks:
        raise ExecutionContractError("contract.checks must contain at least one check")
    seen: set[str] = set()
    for idx, raw in enumerate(checks):
        item = _validate_check(raw, idx)
        check_id = item["id"]
        if check_id in seen:
            raise ExecutionContractError(f"duplicate contract check id: {check_id}")
        seen.add(check_id)
    return root


def _iter_phases_through(phase: str) -> Iterable[str]:
    if phase not in PHASES:
        raise ExecutionContractError(f"phase must be one of {PHASES}")
    end = PHASES.index(phase)
    return PHASES[: end + 1]


def evaluate_contract(data: dict[str, Any], *, phase: str) -> dict[str, Any]:
    """Evaluate material ontology checks through ``phase`` and fail closed.

    Missing referenced facts are not silently ignored. They become UNRESOLVED and
    prevent a PASS for that phase. Warnings are preserved but do not block.
    """
    root = validate_contract(data)
    active_phases = set(_iter_phases_through(phase))
    results: list[dict[str, Any]] = []

    for check in root["checks"]:
        if check["phase"] not in active_phases:
            continue
        left_operand = check["left"]
        right_operand = check.get("right")
        try:
            left = _operand_value(root, left_operand, f"check {check['id']}.left")
            right = (
                _operand_value(root, right_operand, f"check {check['id']}.right")
                if right_operand is not None
                else None
            )
        except KeyError as exc:
            results.append(
                {
                    "id": check["id"],
                    "phase": check["phase"],
                    "meaning": check["meaning"],
                    "severity": check.get("severity", "hard"),
                    "status": "UNRESOLVED",
                    "missing_path": str(exc.args[0]),
                    "on_fail": check.get("on_fail", "EXECUTION_CONTRACT_UNRESOLVED"),
                }
            )
            continue

        passed = _evaluate_operator(check["op"], left, right)
        results.append(
            {
                "id": check["id"],
                "phase": check["phase"],
                "meaning": check["meaning"],
                "severity": check.get("severity", "hard"),
                "status": "PASS" if passed else "FAIL",
                "left": left,
                "op": check["op"],
                "right": right,
                "on_fail": check.get("on_fail", "EXECUTION_CONTRACT_FAIL"),
            }
        )

    blockers = [
        item
        for item in results
        if item["severity"] in {"hard", "hold"}
        and item["status"] in {"FAIL", "UNRESOLVED"}
    ]
    warnings = [
        item
        for item in results
        if item["severity"] == "warn" and item["status"] != "PASS"
    ]

    requested_decision = root["decision"]["status"]
    ontology_pass = not blockers
    if phase == "DECISION" and requested_decision == "PASS" and not ontology_pass:
        status = "REJECTED_PASS"
    elif ontology_pass:
        status = "PASS"
    else:
        status = "HOLD"

    return {
        "schema_version": SCHEMA_VERSION,
        "contract_id": root["contract_id"],
        "phase": phase,
        "status": status,
        "ontology_conformant": ontology_pass,
        "requested_decision": requested_decision,
        "blockers": blockers,
        "warnings": warnings,
        "checks": results,
    }


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionContractError(f"failed to read contract {path}: {exc}") from exc
    return _mapping(value, "contract")


def self_test() -> int:
    try:
        base: dict[str, Any] = {
            "schema_version": 1,
            "contract_id": "synthetic-fixed-step",
            "claim": {
                "statement": "exercise five intended physical timesteps",
                "acceptance": "five physical rows and preserved fixed-step semantics",
            },
            "model": {
                "representation": "synthetic transient",
                "retained": ["transient state"],
                "reduced": [],
                "assumptions": ["fixed-step semantics are part of the claim"],
            },
            "numerical_regime": {
                "intent": "fixed-step discriminator",
                "declared_controls": {
                    "dt": 1.0e-13,
                    "num_steps": 5,
                    "end_time": 5.0e-13,
                },
                "declared_scales": {"tau": 1.0e-12},
            },
            "framework_effective": {
                "provenance": "synthetic executable introspection",
                "controls": {
                    "dtmin": 1.0e-14,
                    "timestep_tolerance": 1.0e-16,
                    "adaptivity": False,
                },
            },
            "runtime_regime": {
                "observed": {
                    "physical_rows": 5,
                    "final_time": 5.0e-13,
                    "actual_dt": 1.0e-13,
                }
            },
            "evidence": {
                "requirements": ["physical timestep rows", "final physical time"],
                "observed": {"checker_status": "PASS"},
            },
            "decision": {"status": "PASS"},
            "checks": [
                {
                    "id": "dt-above-dtmin",
                    "phase": "P1",
                    "meaning": "requested dt must exceed effective dtmin",
                    "left": {"path": "numerical_regime.declared_controls.dt"},
                    "op": "gt",
                    "right": {"path": "framework_effective.controls.dtmin"},
                    "on_fail": "NUMERICAL_CONTRACT_FAIL",
                },
                {
                    "id": "time-tolerance-below-dt",
                    "phase": "P1",
                    "meaning": "framework timestep tolerance must be below requested dt",
                    "left": {"path": "framework_effective.controls.timestep_tolerance"},
                    "op": "lt",
                    "right": {"path": "numerical_regime.declared_controls.dt"},
                    "on_fail": "NUMERICAL_CONTRACT_FAIL",
                },
                {
                    "id": "physical-row-count",
                    "phase": "P3",
                    "meaning": "runtime must emit the intended number of physical rows",
                    "left": {"path": "runtime_regime.observed.physical_rows"},
                    "op": "ge",
                    "right": {"path": "numerical_regime.declared_controls.num_steps"},
                    "on_fail": "RUNTIME_SEMANTIC_FAIL",
                },
                {
                    "id": "actual-fixed-dt",
                    "phase": "P3",
                    "meaning": "runtime must preserve the requested fixed timestep",
                    "left": {"path": "runtime_regime.observed.actual_dt"},
                    "op": "eq",
                    "right": {"path": "numerical_regime.declared_controls.dt"},
                    "on_fail": "RUNTIME_SEMANTIC_FAIL",
                },
                {
                    "id": "evidence-checker",
                    "phase": "DECISION",
                    "meaning": "declared evidence checker must pass",
                    "left": {"path": "evidence.observed.checker_status"},
                    "op": "eq",
                    "right": {"value": "PASS"},
                    "on_fail": "EVIDENCE_CONTRACT_FAIL",
                },
            ],
        }

        if evaluate_contract(base, phase="DECISION")["status"] != "PASS":
            raise AssertionError("positive ontology contract did not pass")

        bad_dt = json.loads(json.dumps(base))
        bad_dt["framework_effective"]["controls"]["dtmin"] = 1.0e-12
        result = evaluate_contract(bad_dt, phase="P1")
        if result["status"] != "HOLD" or not result["blockers"]:
            raise AssertionError("dt/dtmin contradiction was not blocked")

        missing_runtime = json.loads(json.dumps(base))
        del missing_runtime["runtime_regime"]["observed"]["physical_rows"]
        result = evaluate_contract(missing_runtime, phase="P3")
        if result["status"] != "HOLD" or result["blockers"][0]["status"] not in {
            "FAIL",
            "UNRESOLVED",
        }:
            raise AssertionError("missing runtime evidence did not fail closed")

        bad_decision = json.loads(json.dumps(base))
        bad_decision["evidence"]["observed"]["checker_status"] = "FAIL"
        result = evaluate_contract(bad_decision, phase="DECISION")
        if result["status"] != "REJECTED_PASS":
            raise AssertionError("invalid requested PASS was not rejected")

        duplicate = json.loads(json.dumps(base))
        duplicate["checks"].append(dict(duplicate["checks"][0]))
        try:
            validate_contract(duplicate)
        except ExecutionContractError:
            pass
        else:
            raise AssertionError("duplicate check id was not rejected")
    except Exception as exc:
        print(f"EXECUTION_CONTRACT_SELFTEST: FAIL ({exc})")
        return 1
    print("EXECUTION_CONTRACT_SELFTEST: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate/evaluate a CORE-16 scientific execution contract"
    )
    parser.add_argument("contract", nargs="?", help="execution-contract JSON file")
    parser.add_argument(
        "--phase",
        choices=PHASES,
        default="DECISION",
        help="evaluate ontology checks through this phase",
    )
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--json-out")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.contract:
        parser.error("contract JSON path is required unless --self-test is used")

    path = Path(args.contract).expanduser().resolve()
    try:
        data = _load(path)
        if args.schema_only:
            root = validate_contract(data)
            result: dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "contract_id": root["contract_id"],
                "status": "SCHEMA_PASS",
            }
        else:
            result = evaluate_contract(data, phase=args.phase)
    except ExecutionContractError as exc:
        result = {
            "schema_version": SCHEMA_VERSION,
            "status": "CONTRACT_INVALID",
            "error": str(exc),
        }

    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.json_out:
        Path(args.json_out).expanduser().resolve().write_text(text)
    return 0 if result.get("status") in {"SCHEMA_PASS", "PASS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
