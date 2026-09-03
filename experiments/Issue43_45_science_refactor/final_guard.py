#!/usr/bin/env python3
"""Static gate for the joint Issue43/Issue45 science refactor."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import issue43_fast_relaxation as legacy_issue43_v5
from qpx_harness import issue43_relaxation_runtime as issue43_runtime
from qpx_harness.issue43_coupling import analysis as issue43_analysis
from qpx_harness.petsc import ksp
from qpx_harness.spec.cases import QVT_PREPOISSON_CASE
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
    issue43_constants = (ROOT / "qpx_harness/issue43_coupling/constants.py").read_text()
    inventory_constants = (ROOT / "qpx_harness/inventory/constants.py").read_text()
    assert "QVT_PREPOISSON_CASE" in issue43_constants
    assert "QVT_PREPOISSON_CASE" in inventory_constants
    assert "issue43_coupling_diagnostic" not in inventory_constants

    coupled_policy_path = ROOT / "qpx_harness/diagnose/presets/coupled_solver.py"
    imports = _imports(coupled_policy_path)
    assert not any(module.startswith("recipes") for module in imports), imports
    assert not any(module.startswith("qpx_harness.issue") for module in imports), imports
    source43 = (ROOT / "qpx_harness/issue43_coupling/analysis.py").read_text()
    assert "runtime_core_facts" in source43
    assert "diagnose_coupled_runtime_evidence" in source43
    assert issue43_analysis._line_hits is not None

    fixture = issue43_runtime._fixture()
    canonical_feedback, basis_meta = issue45_closure_basis.build_closed_feedback_input(
        fixture,
        radial_span=0.243,
        dt=issue43_runtime.DT_FEEDBACK_BASE,
        steps=issue43_runtime.N_STEPS,
    )
    legacy_feedback = legacy_issue43_v5._build_feedback_v5(
        fixture,
        dt=issue43_runtime.DT_FEEDBACK_BASE,
        steps=issue43_runtime.N_STEPS,
        radial_span=0.243,
    )
    assert canonical_feedback == legacy_feedback
    assert basis_meta["versioned_qpx_facade_dependency"] is False

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

    legacy_issue45_root = ROOT / "qpx_harness/issue45"
    if legacy_issue45_root.exists():
        for path in legacy_issue45_root.glob("*.py"):
            if path.name == "__init__.py":
                continue
            source = path.read_text()
            assert "Compatibility adapter" in source, path
            tree = ast.parse(source, filename=str(path))
            assert not any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                for node in tree.body
            ), path

    cli_source = (ROOT / "qpx_harness/cli/app.py").read_text()
    # Issue120 keeps the same canonical inventory owners but resolves legacy
    # commands lazily so unrelated scientific modules cannot break -i/-e startup.
    assert '"inventory-nullspace": "qpx_harness.inventory.cli:inventory_main"' in cli_source
    assert '"inventory-first-linear": "qpx_harness.inventory.cli:first_linear_main"' in cli_source
    assert "qpx_harness.electron_inventory_nullspace" not in cli_source
    assert "qpx_harness.issue45_first_linear" not in cli_source

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

    print("ISSUE43_45_SHARED_CASE_IDENTITY: PASS")
    print("ISSUE43_45_CANONICAL_EVIDENCE_DIAGNOSE_PIPELINE: PASS")
    print("ISSUE43_45_FEEDBACK_BASIS_EQUIVALENCE: PASS")
    print("ISSUE45_CANONICAL_INVENTORY_PACKAGE: PASS")
    print("ISSUE45_LEGACY_PACKAGE_IMPLEMENTATION_OWNERS: 0")
    print("ISSUE45_CLI_CANONICAL_CUTOVER: PASS")
    print("ISSUE45_RECIPE_POLICY_CONVERGENCE: PASS")
    print("ISSUE45_KSP_RESIDUAL_FIDELITY_AUDIT: PASS")
    print("ISSUE45_RESTART_CAUSALITY: NOT_ESTABLISHED")
    print("ISSUE43_EVRS_CONSUMED_BY_REFACTOR: 0")
    print("ISSUE45_EVRS_CONSUMED_BY_REFACTOR: 0")
    print("ISSUE43_45_SCIENCE_REFACTOR_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
