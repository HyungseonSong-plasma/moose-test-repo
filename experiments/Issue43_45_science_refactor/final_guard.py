#!/usr/bin/env python3
"""Static gate for canonicalized Issue43/Issue45 science ownership after #144."""
from __future__ import annotations
import ast, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from qpx_harness.evidence import extract_jacobian_evidence, runtime_core_facts
from qpx_harness.petsc import ksp
from qpx_harness.reasoning import diagnose_coupled_runtime_evidence
from qpx_harness.reasoning.jacobian import diagnose_jacobian_evidence
from qpx_harness.provenance.cases import QVT_PREPOISSON_CASE
from qpx_harness.adapters.moose.electron_inventory import feedback_basis, closure_basis, first_linear
from qpx_harness.analysis.electron_inventory.first_linear_runtime import analyze_first_linear_text

def _imports(path: Path) -> set[str]:
    tree=ast.parse(path.read_text(), filename=str(path)); modules=set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): modules.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module: modules.add(node.module)
    return modules

def main() -> int:
    assert QVT_PREPOISSON_CASE == Path("experiments/Issue2_electron_bulk_drift/qvt_prepoisson")
    assert not (ROOT / "qpx_harness/inventory").exists()
    assert not (ROOT / "recipes").exists()
    assert callable(feedback_basis.build_closed_feedback_input)
    assert callable(closure_basis.build_constrained_quasisteady_input)
    assert callable(first_linear.instrument_first_linear)
    assert callable(analyze_first_linear_text)
    assert closure_basis.DT_REFERENCE == feedback_basis.DT_REFERENCE
    assert closure_basis.STEPS == feedback_basis.STEPS
    for path in [ROOT/"qpx_harness/reasoning/coupled_solver.py", ROOT/"qpx_harness/adapters/moose/electron_inventory/closure_basis.py"]:
        imports=_imports(path)
        assert not any(m.startswith("recipes") for m in imports), imports
        assert not any(m.startswith("experiments.historical_recipe_support") for m in imports), imports
    assert callable(runtime_core_facts) and callable(extract_jacobian_evidence)
    assert callable(diagnose_coupled_runtime_evidence) and callable(diagnose_jacobian_evidence)
    cli_source=(ROOT/"qpx_harness/cli/app.py").read_text()
    assert '"inventory-nullspace": "qpx_harness.cli.commands.inventory:inventory_main"' in cli_source
    assert '"inventory-first-linear": "qpx_harness.cli.commands.inventory:first_linear_main"' in cli_source
    rows=[{"iteration":0,"reported_residual":8e-3,"true_residual":8e-3,"relative_true_residual":1.0},{"iteration":30,"reported_residual":1e-12,"true_residual":2e-3,"relative_true_residual":2.5e-1}]
    audit=ksp.residual_fidelity_audit(rows,restart=30,ratio_threshold=1e6)
    assert audit["residual_fidelity_loss_observed"] is True
    assert audit["worst_iteration"] == 30 and audit["worst_at_restart_boundary"] is True
    assert audit["causal_attribution"] == "NOT_ESTABLISHED"
    source=(ROOT/"qpx_harness/analysis/electron_inventory/first_linear_runtime.py").read_text()
    assert "GMRES_RESTART_BREAKDOWN" not in source
    assert "KSP_BREAKDOWN_RESIDUAL_FIDELITY_LOSS" in source
    assert 'restart_causality="NOT_ESTABLISHED"' in source
    print("ISSUE43_45_SHARED_CASE_IDENTITY: PASS")
    print("ISSUE43_CANONICAL_FEEDBACK_OWNERSHIP: PASS")
    print("ISSUE45_CANONICAL_INVENTORY_OWNERSHIP: PASS")
    print("ISSUE45_KSP_RESIDUAL_FIDELITY_AUDIT: PASS")
    print("ISSUE43_45_SCIENCE_REFACTOR_GUARD: PASS")
    return 0
if __name__ == "__main__": raise SystemExit(main())
