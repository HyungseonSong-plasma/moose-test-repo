from __future__ import annotations

import json
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.adapters.moose.mutation_spec import (
    MutationSpecError,
    OperationPlan,
    compile_mutation_spec,
    load_mutation_json_text,
    load_mutation_payload,
    pydantic_major_api,
)
from qpx_harness.adapters.moose.transforms import (
    SUPPORTED_OPERATIONS,
    TransformError,
    apply_case_plan,
    apply_operation,
)


BASE_INPUT = """[Executioner]
  type = Transient
  petsc_options = '-existing'
[]
[Outputs]
  [console]
    type = Console
  []
[]
"""

VALID_PAYLOAD = {
    "schema_version": 1,
    "experiment_id": "generic-diagnostic-pilot",
    "description": "generic schema characterization only",
    "cases": [
        {
            "case_id": "default",
            "operations": [
                {
                    "op": "ensure_block",
                    "path": "Debug",
                    "block": "[Debug]\n[]",
                },
                {
                    "op": "set_parameter",
                    "path": "Debug",
                    "name": "show_var_residual_norms",
                    "value": "true",
                },
                {
                    "op": "set_parameter",
                    "path": "Executioner",
                    "name": "verbose",
                    "value": "true",
                },
                {
                    "op": "add_petsc_flags",
                    "flags": [
                        "-snes_converged_reason",
                        "-ksp_converged_reason",
                    ],
                },
                {
                    "op": "set_parameter",
                    "path": "Outputs/console",
                    "name": "all_variable_norms",
                    "value": "true",
                },
            ],
        },
        {
            "case_id": "jacobian",
            "operations": [
                {
                    "op": "ensure_block",
                    "path": "Debug",
                    "block": "[Debug]\n[]",
                },
                {
                    "op": "add_petsc_flags",
                    "flags": ["-snes_test_jacobian"],
                },
            ],
        },
    ],
}


def expect_error(payload: object) -> None:
    try:
        load_mutation_payload(payload)
    except MutationSpecError:
        return
    raise AssertionError("invalid ExperimentSpec payload was accepted")


def main() -> int:
    failures: list[str] = []

    try:
        spec = load_mutation_payload(VALID_PAYLOAD)
        text = json.dumps(VALID_PAYLOAD)
        roundtrip = load_mutation_json_text(text)
        assert spec == roundtrip
    except Exception as exc:
        failures.append(f"positive schema: {exc}")
        print(f"ISSUE60_POSITIVE_SCHEMA: FAIL ({exc})")
        spec = None
    else:
        print(f"ISSUE60_POSITIVE_SCHEMA: PASS pydantic_api={pydantic_major_api()}")

    if spec is not None:
        try:
            first = compile_mutation_spec(spec)
            second = compile_mutation_spec(load_mutation_payload(json.loads(json.dumps(VALID_PAYLOAD))))
            assert first == second
        except Exception as exc:
            failures.append(f"deterministic plan: {exc}")
            print(f"ISSUE60_DETERMINISTIC_PLAN: FAIL ({exc})")
            plan = None
        else:
            plan = first
            print("ISSUE60_DETERMINISTIC_PLAN: PASS")

        try:
            source_root = ROOT / "qpx_harness" / "adapters" / "moose" / "mutation_spec"
            combined = "\n".join(
                path.read_text(encoding="utf-8")
                for path in sorted(source_root.glob("*.py"))
            )
            forbidden = ("qpx_harness.runtime", "run_qpx", "resolve_executable")
            assert not any(token in combined for token in forbidden)
        except Exception as exc:
            failures.append(f"runtime side effect boundary: {exc}")
            print(f"ISSUE60_RUNTIME_SIDE_EFFECT_FREE: FAIL ({exc})")
        else:
            print("ISSUE60_RUNTIME_SIDE_EFFECT_FREE: PASS")

        try:
            bad_extra = json.loads(json.dumps(VALID_PAYLOAD))
            bad_extra["unexpected"] = True
            expect_error(bad_extra)

            bad_nested = json.loads(json.dumps(VALID_PAYLOAD))
            bad_nested["cases"][0]["operations"][0]["unexpected"] = 1
            expect_error(bad_nested)

            bad_version = json.loads(json.dumps(VALID_PAYLOAD))
            bad_version["schema_version"] = 2
            expect_error(bad_version)
        except Exception as exc:
            failures.append(f"negative schema: {exc}")
            print(f"ISSUE60_NEGATIVE_SCHEMA: FAIL ({exc})")
        else:
            print("ISSUE60_NEGATIVE_SCHEMA: PASS")

        try:
            bad_op = json.loads(json.dumps(VALID_PAYLOAD))
            bad_op["cases"][0]["operations"][0] = {"op": "arbitrary_python"}
            expect_error(bad_op)
        except Exception as exc:
            failures.append(f"unknown operation: {exc}")
            print(f"ISSUE60_UNKNOWN_OPERATION_REJECTION: FAIL ({exc})")
        else:
            print("ISSUE60_UNKNOWN_OPERATION_REJECTION: PASS")

        if plan is not None:
            try:
                try:
                    plan.schema_version = 2  # type: ignore[misc]
                except FrozenInstanceError:
                    pass
                else:
                    raise AssertionError("MutationPlan is mutable")
            except Exception as exc:
                failures.append(f"plan immutability: {exc}")
                print(f"ISSUE60_PLAN_IMMUTABILITY: FAIL ({exc})")
            else:
                print("ISSUE60_PLAN_IMMUTABILITY: PASS")

            try:
                assert SUPPORTED_OPERATIONS == {
                    "ensure_block",
                    "set_parameter",
                    "add_petsc_flags",
                }
            except Exception as exc:
                failures.append(f"registry boundary: {exc}")
                print(f"ISSUE61_REGISTRY_BOUNDARY: FAIL ({exc})")
            else:
                print("ISSUE61_REGISTRY_BOUNDARY: PASS")

            try:
                rendered = apply_case_plan(BASE_INPUT, plan.case("default"))
                assert "[Debug]" in rendered
                assert "show_var_residual_norms = true" in rendered
                assert "verbose = true" in rendered
                assert "all_variable_norms = true" in rendered
                assert "-existing" in rendered
                assert "-snes_converged_reason" in rendered
                assert "-ksp_converged_reason" in rendered
            except Exception as exc:
                failures.append(f"transform application: {exc}")
                print(f"ISSUE61_TRANSFORM_APPLICATION: FAIL ({exc})")
                rendered = None
            else:
                print("ISSUE61_TRANSFORM_APPLICATION: PASS")

            if rendered is not None:
                try:
                    twice = apply_case_plan(rendered, plan.case("default"))
                    assert twice == rendered
                except Exception as exc:
                    failures.append(f"idempotence: {exc}")
                    print(f"ISSUE61_IDEMPOTENCE: FAIL ({exc})")
                else:
                    print("ISSUE61_IDEMPOTENCE: PASS")

            try:
                ordered_payload = {
                    "schema_version": 1,
                    "experiment_id": "order-check",
                    "cases": [
                        {
                            "case_id": "ordered",
                            "operations": [
                                {
                                    "op": "set_parameter",
                                    "path": "Executioner",
                                    "name": "verbose",
                                    "value": "false",
                                },
                                {
                                    "op": "set_parameter",
                                    "path": "Executioner",
                                    "name": "verbose",
                                    "value": "true",
                                },
                            ],
                        }
                    ],
                }
                ordered = compile_mutation_spec(load_mutation_payload(ordered_payload))
                output = apply_case_plan(BASE_INPUT, ordered.case("ordered"))
                assert "verbose = true" in output
                assert "verbose = false" not in output
            except Exception as exc:
                failures.append(f"operation order: {exc}")
                print(f"ISSUE61_OPERATION_ORDER: FAIL ({exc})")
            else:
                print("ISSUE61_OPERATION_ORDER: PASS")

            try:
                duplicate_base = BASE_INPUT + "[Debug]\n[]\n[Debug]\n[]\n"
                apply_operation(
                    duplicate_base,
                    OperationPlan(
                        op="ensure_block",
                        arguments=(("path", "Debug"), ("block", "[Debug]\n[]")),
                    ),
                )
            except TransformError:
                print("ISSUE61_DUPLICATE_BLOCK_REJECTION: PASS")
            except Exception as exc:
                failures.append(f"duplicate block rejection: {exc}")
                print(f"ISSUE61_DUPLICATE_BLOCK_REJECTION: FAIL ({exc})")
            else:
                failures.append("duplicate block was accepted")
                print("ISSUE61_DUPLICATE_BLOCK_REJECTION: FAIL")

            try:
                apply_operation(BASE_INPUT, OperationPlan(op="unknown", arguments=()))
            except TransformError:
                print("ISSUE61_UNKNOWN_REGISTRY_OPERATION: PASS")
            except Exception as exc:
                failures.append(f"unknown registry operation: {exc}")
                print(f"ISSUE61_UNKNOWN_REGISTRY_OPERATION: FAIL ({exc})")
            else:
                failures.append("registry accepted unknown operation")
                print("ISSUE61_UNKNOWN_REGISTRY_OPERATION: FAIL")

            try:
                source_root = ROOT / "qpx_harness" / "transforms"
                combined = "\n".join(
                    path.read_text(encoding="utf-8").lower()
                    for path in sorted(source_root.glob("*.py"))
                )
                forbidden = ("issue31", "issue43", "issue45", "issue46")
                assert not any(token in combined for token in forbidden)
            except Exception as exc:
                failures.append(f"issue leakage: {exc}")
                print(f"ISSUE61_ISSUE_LEAKAGE_GUARD: FAIL ({exc})")
            else:
                print("ISSUE61_ISSUE_LEAKAGE_GUARD: PASS")

    print("ISSUE60_REFACTOR_EVRS: 0")
    print("ISSUE61_REFACTOR_EVRS: 0")
    if failures:
        for failure in failures:
            print(f"ISSUE60_61_ERROR: {failure}")
        print("ISSUE60_61_FINAL_GUARD: FAIL")
        return 1
    print("ISSUE60_61_FINAL_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
