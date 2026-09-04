#!/usr/bin/env python3
"""Static gate for the canonicalized Issue43/Issue45 science ownership."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.diagnose import diagnose_coupled_runtime_evidence, diagnose_jacobian_evidence
from qpx_harness.evidence import extract_jacobian_evidence, runtime_core_facts
from qpx_harness.petsc import ksp
from qpx_harness.spec.cases import QVT_PREPOISSON_CASE
from recipes import issue43_feedback_basis
from recipes import issue45_closure_basis
from recipes import issue45_first_linear as issue45_recipe


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def main() -> int:
    expected_case = Path("experiments/Issue2_electron_bulk_drift/qvt_prepoisson")
    assert QVT_PREPOISSON_CASE == expected_case

    # Accepted Issue43 science remains recipe-owned; reusable mechanics are
    # canonical qpx_harness capabilities and no issue-numbered runtime facade
    # is required by the feedback basis.
    feedback_source = (ROOT / "recipes/issue43_feedback_basis.py").read_text()
    assert "versioned_qpx_facade_dependency" in feedback_source
    assert "qpx_harness.issue" not in feedback_source
    assert callable(issue43_feedback_basis.build_closed_feedback_input)
    assert issue45_closure_basis.DT_REFERENCE == issue43_feedback_basis.DT_REFERENCE
    assert issue45_closure_basis.STEPS == issue43_feedback_basis.STEPS

    coupled_policy_path = ROOT / "qpx_harness/diagnose/presets/coupled_solver.py"
    imports = _imports(coupled_policy_path)
    assert not any(module.startswith("recipes") for module in imports), imports
    assert not any(module.startswith("qpx_harness.issue") for module in imports), imports
    assert callable(runtime_core_facts)
    assert callable(extract_jacobian_evidence)
    assert callable(diagnose_coupled_runtime_evidence)
    assert callable(diagnose_jacobian_evidence)

    canonical_inventory_files = {
        "__init__.py",
        "characterization.py",
        "cli.py",
        "closure_model.py",
        "closure_runtime.py",
        "closure_schema.py",
        "constants.py",
        "errors.py",
        "first_linear_characterization.py",
        "first_linear_orchestration.py",
        "first_linear_stats.py",
        "first_linear_structure.py",
        "orchestration.py",
        "structure.py",
    }
    inventory_root = ROOT / "qpx_harness/inventory"
    assert canonical_inventory_files.issubset(
        {path.name for path in inventory_root.glob("*.py")}
    )
    inventory_orchestration_source = (inventory_root / "orchestration.py").read_text()
    assert "issue43_coupling_diagnostic" not in inventory_orchestration_source
    assert "issue43_fast_relaxation" not in inventory_orchestration_source
    assert "runtime_core_facts" in inventory_orchestration_source
    assert "diagnose_coupled_runtime_evidence" in inventory_orchestration_source
    assert "check_input_diagnostic.classify_failure" in inventory_orchestration_source
    first_characterization_source = (
        inventory_root / "first_linear_characterization.py"
    ).read_text()
    assert "electron_inventory_nullspace" not in first_characterization_source
    assert "_synthetic_constrained_input" in first_characterization_source

    cli_source = (ROOT / "qpx_harness/cli/app.py").read_text()
    assert '"inventory-nullspace": "qpx_harness.inventory.cli:inventory_main"' in cli_source
    assert '"inventory-first-linear": "qpx_harness.inventory.cli:first_linear_main"' in cli_source
    for retired_target in (
        "qpx_harness.issue43",
        "qpx_harness.issue45",
        "qpx_harness.issue46",
        "qpx_harness.coupling_evr",
        "qpx_harness.electron_inventory_nullspace",
    ):
        assert retired_target not in cli_source

    rows = [
        {
            "iteration": 0,
            "reported_residual": 8.0e-3,
            "true_residual": 8.0e-3,
            "relative_true_residual": 1.0,
        },
        {
            "iteration": 30,
            "reported_residual": 1.0e-12,
            "true_residual": 2.0e-3,
            "relative_true_residual": 2.5e-1,
        },
    ]
    audit = ksp.residual_fidelity_audit(rows, restart=30, ratio_threshold=1.0e6)
    assert audit["residual_fidelity_loss_observed"] is True, audit
    assert audit["worst_iteration"] == 30, audit
    assert audit["worst_at_restart_boundary"] is True, audit
    assert audit["causal_attribution"] == "NOT_ESTABLISHED", audit

    recipe_source = (ROOT / "recipes/issue45_first_linear.py").read_text()
    assert "GMRES_RESTART_BREAKDOWN" not in recipe_source
    assert "KSP_BREAKDOWN_RESIDUAL_FIDELITY_LOSS" in recipe_source
    assert "restart_causality=\"NOT_ESTABLISHED\"" in recipe_source
    assert issue45_recipe is not None

    print("ISSUE43_45_SHARED_CASE_IDENTITY: PASS")
    print("ISSUE43_CANONICAL_RECIPE_OWNERSHIP: PASS")
    print("ISSUE43_CANONICAL_EVIDENCE_DIAGNOSE_PIPELINE: PASS")
    print("ISSUE45_CANONICAL_INVENTORY_PACKAGE: PASS")
    print("ISSUE45_CLI_CANONICAL_CUTOVER: PASS")
    print("ISSUE45_RECIPE_POLICY_CONVERGENCE: PASS")
    print("ISSUE45_KSP_RESIDUAL_FIDELITY_AUDIT: PASS")
    print("ISSUE45_RESTART_CAUSALITY: NOT_ESTABLISHED")
    print("ISSUE43_45_VERSIONED_QPX_FACADE_DEPENDENCIES: 0")
    print("ISSUE43_45_SCIENCE_REFACTOR_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
