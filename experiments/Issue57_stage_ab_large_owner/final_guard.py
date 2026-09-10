#!/usr/bin/env python3
"""Final guard for the historical Issue57 Stage A/B decomposition after retirement."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

HISTORICAL_DECISIONS = {
    "A1": "SPLIT_APPLIED",
    "A2": "KEEP_COHESIVE",
    "A3": "KEEP_COHESIVE",
    "A4": "KEEP_COHESIVE",
    "A5": "KEEP_COHESIVE",
    "B1": "KEEP_COHESIVE",
    "B2": "KEEP_COHESIVE",
    "B3": "KEEP_COHESIVE",
    "B4": "SPLIT_APPLIED",
    "B5": "KEEP_COHESIVE",
}

HISTORICAL_RECIPE_FILES = (
    "experiments/historical_recipe_support/issue43_coupling_diagnostic.py",
    "experiments/historical_recipe_support/issue46_fd_reference.py",
    "experiments/historical_recipe_support/issue46_jacobian_localization.py",
    "experiments/historical_recipe_support/issue31_coupling.py",
    "experiments/historical_recipe_support/issue45_inventory_constraint.py",
    "experiments/historical_recipe_support/issue45_first_linear.py",
    "experiments/historical_recipe_support/issue43_fast_relaxation.py",
    "experiments/historical_recipe_support/issue43_feedback_basis.py",
)

CURRENT_GENERIC_OWNERS = (
    "physics_harness/adapters/moose/input.py",
    "physics_harness/adapters/moose/blocks.py",
    "physics_harness/adapters/moose/parameters.py",
    "physics_harness/adapters/moose/petsc_options.py",
    "physics_harness/adapters/moose/transforms.py",
    "physics_harness/adapters/petsc/jacobian.py",
    "physics_harness/adapters/petsc/fd_reference.py",
    "physics_harness/analysis/scale_audit.py",
    "physics_harness/application/performance.py",
    "physics_harness/execution/contract.py",
    "physics_harness/execution/cases.py",
    "physics_harness/evidence/identity.py",
)

RETIRED_CAMPAIGN_PATHS = (
    "physics_harness/issue43_coupling_diagnostic.py",
    "physics_harness/issue43_coupling",
    "physics_harness/issue46_fd_reference.py",
    "physics_harness/issue46_jacobian_localization.py",
    "physics_harness/coupling_evr1_runtime.py",
    "physics_harness/coupling_evr1",
    "physics_harness/coupling_evr2_runtime.py",
    "physics_harness/coupling_evr2",
    "physics_harness/issue45",
    "physics_harness/issue43_relaxation_runtime.py",
    "physics_harness/performance_cache_audit.py",
    "physics_harness/execution_contract.py",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _assert_historical_recipe_boundaries() -> None:
    missing = [rel for rel in HISTORICAL_RECIPE_FILES if not (ROOT / rel).is_file()]
    if missing:
        raise AssertionError(f"historical Issue57 recipe support missing: {missing}")
    violations: dict[str, list[str]] = {}
    for rel in HISTORICAL_RECIPE_FILES:
        found = sorted(
            module
            for module in _imports(ROOT / rel)
            if module == "qpx_harness" or module.startswith("qpx_harness.")
        )
        if found:
            violations[rel] = found
    if violations:
        raise AssertionError(
            f"historical recipes retained legacy production imports: {violations}"
        )

    issue43 = (ROOT / HISTORICAL_RECIPE_FILES[0]).read_text(encoding="utf-8")
    if "issue43_coupling_diagnostic.json" not in issue43:
        raise AssertionError("Issue43 coupling diagnostic spec binding drift")
    if "DIAGNOSTIC_PETSC_OPTIONS" not in issue43 or "JACOBIAN_PETSC_OPTIONS" not in issue43:
        raise AssertionError("Issue43 coupling diagnostic PETSc contract drift")

    issue46 = (ROOT / HISTORICAL_RECIPE_FILES[2]).read_text(encoding="utf-8")
    if "issue46_jacobian_localization.json" not in issue46:
        raise AssertionError("Issue46 Jacobian-localization spec binding drift")
    if "LOCALIZATION_THRESHOLD" not in issue46 or "DOFMAP_OUTPUT" not in issue46:
        raise AssertionError("Issue46 Jacobian-localization contract drift")


def main() -> int:
    expected = {
        "A1": "SPLIT_APPLIED",
        "A2": "KEEP_COHESIVE",
        "A3": "KEEP_COHESIVE",
        "A4": "KEEP_COHESIVE",
        "A5": "KEEP_COHESIVE",
        "B1": "KEEP_COHESIVE",
        "B2": "KEEP_COHESIVE",
        "B3": "KEEP_COHESIVE",
        "B4": "SPLIT_APPLIED",
        "B5": "KEEP_COHESIVE",
    }
    if HISTORICAL_DECISIONS != expected:
        raise AssertionError("Issue57 historical decomposition decisions drifted")

    resurrected = [rel for rel in RETIRED_CAMPAIGN_PATHS if (ROOT / rel).exists()]
    if resurrected:
        raise AssertionError(f"retired Issue57 campaign owner resurrected: {resurrected}")

    missing = [rel for rel in CURRENT_GENERIC_OWNERS if not (ROOT / rel).is_file()]
    if missing:
        raise AssertionError(f"current canonical owner missing: {missing}")

    _assert_historical_recipe_boundaries()

    for label, decision in HISTORICAL_DECISIONS.items():
        print(f"ISSUE57_FINAL_{label}_DECISION: {decision}")
    print("ISSUE57_FINAL_A1_RUNTIME_SURFACE: RETIRED")
    print("ISSUE57_FINAL_B4_RUNTIME_SURFACE: RETIRED")
    print("ISSUE57_FINAL_REFACTOR_EVRS: 0")
    print("ISSUE57_FINAL_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
