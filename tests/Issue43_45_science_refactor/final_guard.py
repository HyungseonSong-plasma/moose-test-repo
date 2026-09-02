#!/usr/bin/env python3
"""Static/self-test gate for the joint Issue43/Issue45 science refactor."""
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
from qpx_harness.issue43_coupling import characterization as issue43_characterization
from qpx_harness.issue45 import first_linear_characterization as issue45_characterization
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
    # Shared case identity belongs to canonical spec infrastructure, not one issue.
    expected_case = Path("tests/Issue2_electron_bulk_drift/qvt_prepoisson")
    assert QVT_PREPOISSON_CASE == expected_case
    issue43_constants = (ROOT / "qpx_harness/issue43_coupling/constants.py").read_text()
    issue45_constants = (ROOT / "qpx_harness/issue45/constants.py").read_text()
    assert "QVT_PREPOISSON_CASE" in issue43_constants
    assert "QVT_PREPOISSON_CASE" in issue45_constants
    assert "issue43_coupling_diagnostic" not in issue45_constants

    # Generic coupling facts are capability-owned and may not depend on recipes/issues.
    coupling_path = ROOT / "qpx_harness/diagnostics/coupling.py"
    imports = _imports(coupling_path)
    assert not any(module.startswith("recipes") for module in imports), imports
    assert not any(module.startswith("qpx_harness.issue") for module in imports), imports
    source43 = (ROOT / "qpx_harness/issue43_coupling/analysis.py").read_text()
    assert "coupling_diagnostic.analyze_runtime_failure" in source43
    assert issue43_analysis._line_hits is not None

    # The accepted Issue43 feedback basis is now recipe-owned.  Prove byte
    # equivalence to the historical v5 composition before retiring that facade.
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
    closure_model_source = (ROOT / "qpx_harness/issue45/closure_model.py").read_text()
    assert "issue43_fast_relaxation" not in closure_model_source
    assert "issue45_closure_basis" in closure_model_source

    # KSP residual fidelity is a reusable fact and restart coincidence is non-causal.
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

    # Issue45 policy must preserve this epistemic boundary.
    recipe_source = (ROOT / "recipes/issue45_first_linear.py").read_text()
    assert "GMRES_RESTART_BREAKDOWN" not in recipe_source
    assert "KSP_BREAKDOWN_RESIDUAL_FIDELITY_LOSS" in recipe_source
    assert "restart_causality=\"NOT_ESTABLISHED\"" in recipe_source

    # P0/self-test only: no scientific runtime or EVR is consumed by this guard.
    assert issue43_characterization.self_test() == 0
    assert issue45_characterization.self_test() == 0

    print("ISSUE43_45_SHARED_CASE_IDENTITY: PASS")
    print("ISSUE43_45_CANONICAL_COUPLING_DIAGNOSTICS: PASS")
    print("ISSUE43_45_FEEDBACK_BASIS_EQUIVALENCE: PASS")
    print("ISSUE45_KSP_RESIDUAL_FIDELITY_AUDIT: PASS")
    print("ISSUE45_RESTART_CAUSALITY: NOT_ESTABLISHED")
    print("ISSUE43_EVRS_CONSUMED_BY_REFACTOR: 0")
    print("ISSUE45_EVRS_CONSUMED_BY_REFACTOR: 0")
    print("ISSUE43_45_SCIENCE_REFACTOR_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
