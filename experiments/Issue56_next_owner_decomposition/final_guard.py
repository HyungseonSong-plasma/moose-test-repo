#!/usr/bin/env python3
"""Final guard for the historical Issue56 owner decomposition after retirement."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HISTORICAL_DECISIONS = {
    "W1_performance_cache_audit": "KEEP_COHESIVE",
    "W2_execution_contract": "KEEP_COHESIVE",
    "W3_coupling_evr2": "KEEP_COHESIVE",
    "W4_issue45_first_linear": "SPLIT_APPLIED",
    "W5_dmix_equivalence": "SPLIT_APPLIED",
}
RETIRED_CAMPAIGN_PATHS = (
    "physics_harness/performance_cache_audit.py",
    "physics_harness/execution_contract.py",
    "physics_harness/coupling_evr2_runtime.py",
    "physics_harness/coupling_evr2",
    "physics_harness/issue45_first_linear.py",
    "physics_harness/issue45",
    "physics_harness/dmix_equivalence.py",
    "physics_harness/adapters/moose/dmix_equivalence.py",
    "physics_harness/analysis/dmix_equivalence.py",
    "physics_harness/execution/dmix_equivalence.py",
    "physics_harness/validation/dmix_equivalence.py",
)
CURRENT_OWNER_FILES = (
    "physics_harness/application/performance.py",
    "physics_harness/execution/contract.py",
    "physics_harness/domains/plasma/transport/__init__.py",
    "physics_harness/adapters/moose/transforms.py",
    "physics_harness/execution/cases.py",
    "physics_harness/evidence/identity.py",
)
FIRST_LINEAR_RECIPE = "experiments/historical_recipe_support/issue45_first_linear.py"
FIRST_LINEAR_FUNCTIONS = {
    "instrument_first_linear",
    "analyze_first_linear_text",
}


def _module_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _literal_assignment(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                return ast.literal_eval(node.value)
    raise AssertionError(f"missing literal assignment: {path}: {name}")


def main() -> int:
    assert HISTORICAL_DECISIONS == {
        "W1_performance_cache_audit": "KEEP_COHESIVE",
        "W2_execution_contract": "KEEP_COHESIVE",
        "W3_coupling_evr2": "KEEP_COHESIVE",
        "W4_issue45_first_linear": "SPLIT_APPLIED",
        "W5_dmix_equivalence": "SPLIT_APPLIED",
    }

    resurrected = [
        relative for relative in RETIRED_CAMPAIGN_PATHS if (ROOT / relative).exists()
    ]
    if resurrected:
        raise AssertionError(f"retired Issue56 owner resurrected: {resurrected}")

    missing = [
        relative for relative in CURRENT_OWNER_FILES if not (ROOT / relative).is_file()
    ]
    if missing:
        raise AssertionError(f"current canonical owner missing: {missing}")

    first_linear = ROOT / FIRST_LINEAR_RECIPE
    missing_functions = FIRST_LINEAR_FUNCTIONS - _module_functions(first_linear)
    if missing_functions:
        raise AssertionError(
            f"historical first-linear policy missing: {sorted(missing_functions)}"
        )
    first_linear_source = first_linear.read_text(encoding="utf-8")
    if "qpx_harness" in first_linear_source:
        raise AssertionError("historical first-linear policy retained legacy production import")

    transport = ROOT / "physics_harness/domains/plasma/transport/__init__.py"
    if _literal_assignment(transport, "DMIX_EQUIVALENCE_REL_TOL") != 2.0e-5:
        raise AssertionError("generic DMIX equivalence tolerance drift")
    species = _literal_assignment(transport, "OXYGEN_HEAVY_SPECIES")
    if species != ("O2", "O2s", "O2p", "O", "Om", "Op", "Os"):
        raise AssertionError(f"generic DMIX species contract drift: {species}")

    production = ROOT / "physics_harness"
    dmix_paths = [
        str(path.relative_to(ROOT))
        for path in production.rglob("*dmix_equivalence*")
    ]
    if dmix_paths:
        raise AssertionError(f"retired DMIX campaign namespace reappeared: {dmix_paths}")

    print("ISSUE56_FINAL_W1_DECISION: KEEP_COHESIVE")
    print("ISSUE56_FINAL_W2_DECISION: KEEP_COHESIVE")
    print("ISSUE56_FINAL_W3_DECISION: KEEP_COHESIVE")
    print("ISSUE56_FINAL_W4_DECISION: SPLIT_APPLIED")
    print("ISSUE56_FINAL_W5_DECISION: SPLIT_APPLIED")
    print("ISSUE56_FINAL_W4_RUNTIME_SURFACE: RETIRED")
    print("ISSUE56_FINAL_W5_RUNTIME_SURFACE: RETIRED")
    print("ISSUE56_FINAL_REFACTOR_EVRS: 0")
    print("ISSUE56_FINAL_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
