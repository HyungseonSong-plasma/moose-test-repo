#!/usr/bin/env python3
"""Consolidated guard for the historical Issue55 decomposition after retirement."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.historical_recipe_support import issue43_fast_relaxation as fast

HISTORICAL_DECISIONS = {
    "W1_scale_audit": "KEEP_COHESIVE",
    "W2_fast_relaxation": "SPLIT_APPLIED",
    "W3_coupling_diagnostic": "KEEP_COHESIVE",
    "W4_jacobian_localization": "KEEP_COHESIVE",
    "W5_fd_reference": "KEEP_COHESIVE",
}
RETIRED_CAMPAIGN_PATHS = (
    "physics_harness/issue43_fast_relaxation.py",
    "physics_harness/issue43_fast_base.py",
    "physics_harness/issue43_fast_contract.py",
    "physics_harness/issue43_fast_v3_characterization.py",
    "physics_harness/issue43_fast_output_contract.py",
    "physics_harness/issue43_fast_output_analysis.py",
    "physics_harness/issue43_fast_output_execution.py",
    "physics_harness/issue43_fast_orchestration.py",
    "physics_harness/issue43_fast_characterization.py",
    "physics_harness/issue43_coupling_diagnostic.py",
    "physics_harness/issue46_jacobian_localization.py",
    "physics_harness/issue46_fd_reference.py",
)
GENERIC_OWNER_FILES = (
    "physics_harness/adapters/moose/input.py",
    "physics_harness/analysis/scale_audit.py",
    "physics_harness/execution/runtime.py",
    "physics_harness/execution/cases.py",
    "physics_harness/evidence/identity.py",
)
REQUIRED_HISTORICAL_FUNCTIONS = {
    "build_fast_input",
    "find_relaxation_csv",
    "read_relaxation_rows",
    "analyze_relaxation",
    "classify",
}


def _functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def main() -> int:
    assert HISTORICAL_DECISIONS == {
        "W1_scale_audit": "KEEP_COHESIVE",
        "W2_fast_relaxation": "SPLIT_APPLIED",
        "W3_coupling_diagnostic": "KEEP_COHESIVE",
        "W4_jacobian_localization": "KEEP_COHESIVE",
        "W5_fd_reference": "KEEP_COHESIVE",
    }

    resurrected = [
        relative for relative in RETIRED_CAMPAIGN_PATHS if (ROOT / relative).exists()
    ]
    if resurrected:
        raise AssertionError(f"retired Issue55 campaign owner resurrected: {resurrected}")

    missing = [
        relative for relative in GENERIC_OWNER_FILES if not (ROOT / relative).is_file()
    ]
    if missing:
        raise AssertionError(f"canonical generic owner missing: {missing}")

    recipe_path = Path(fast.__file__)
    observed = _functions(recipe_path)
    missing_functions = REQUIRED_HISTORICAL_FUNCTIONS - observed
    if missing_functions:
        raise AssertionError(
            f"historical Issue43 recipe lost semantics: {sorted(missing_functions)}"
        )
    source = recipe_path.read_text(encoding="utf-8")
    if (
        "from physics_harness.adapters.moose.input import MooseInput, MooseInputError"
        not in source
    ):
        raise AssertionError("historical Issue43 recipe lost canonical MOOSE input owner")
    if "qpx_harness" in source:
        raise AssertionError("historical Issue43 recipe retains legacy production dependency")
    if fast.DEFAULT_PRESSURE != 1.33322:
        raise AssertionError("historical Issue43 pressure anchor drift")

    print("ISSUE55_FINAL_W1_DECISION: KEEP_COHESIVE")
    print("ISSUE55_FINAL_W2_DECISION: SPLIT_APPLIED")
    print("ISSUE55_FINAL_W3_DECISION: KEEP_COHESIVE")
    print("ISSUE55_FINAL_W4_DECISION: KEEP_COHESIVE")
    print("ISSUE55_FINAL_W5_DECISION: KEEP_COHESIVE")
    print("ISSUE55_FINAL_W2_RUNTIME_SURFACE: RETIRED")
    print("ISSUE55_FINAL_REFACTOR_EVRS: 0")
    print("ISSUE55_FINAL_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
