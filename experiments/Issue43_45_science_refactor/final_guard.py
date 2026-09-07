#!/usr/bin/env python3
"""Static gate for Issue43/Issue45 historical science characterization.

Historical Issue43/45 identity remains in experiment/provenance ownership.  The
canonical plasma API is the parameterized species-constraint capability; no
Issue45 electron-inventory production package is required by this guard.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.adapters.moose.nonlinear_solver import runtime_core_facts
from qpx_harness.adapters.petsc import ksp
from qpx_harness.evidence import extract_jacobian_evidence
from qpx_harness.reasoning import diagnose_coupled_runtime_evidence
from qpx_harness.reasoning.jacobian import diagnose_jacobian_evidence
from qpx_harness.provenance.cases import QVT_PREPOISSON_CASE
from qpx_harness.domains.plasma.species_constraints import (
    SpeciesLinearConstraint,
    evaluate_species_constraint,
)


def main() -> int:
    # Historical case identity is provenance, not a canonical production default.
    assert QVT_PREPOISSON_CASE == Path(
        "experiments/Issue2_electron_bulk_drift/qvt_prepoisson"
    )

    # Issue #148 retirement invariant: historical electron-inventory realization
    # may be recovered from Git history/experiment evidence, but is not production
    # architecture ownership.
    for rel in (
        "qpx_harness/domains/plasma/electron_inventory.py",
        "qpx_harness/analysis/electron_inventory",
        "qpx_harness/adapters/moose/electron_inventory",
        "qpx_harness/execution/electron_inventory",
        "qpx_harness/cli/commands/inventory.py",
    ):
        assert not (ROOT / rel).exists(), rel

    assert callable(runtime_core_facts) and callable(extract_jacobian_evidence)
    assert callable(diagnose_coupled_runtime_evidence) and callable(
        diagnose_jacobian_evidence
    )

    cli_source = (ROOT / "qpx_harness/cli/app.py").read_text()
    assert "inventory-nullspace" not in cli_source
    assert "inventory-first-linear" not in cli_source
    assert "dmix-equivalence" not in cli_source

    # Generic species constraints reproduce the accepted inventory/charge-balance
    # proposition without hard-coding electron ownership into the API.
    constraint = SpeciesLinearConstraint(
        {"e": 1.0, "ion": -1.0}, target=0.0, absolute_tolerance=1e-12
    )
    assert evaluate_species_constraint({"e": 2.0, "ion": 2.0}, constraint).satisfied

    # Preserve the previously accepted PETSc residual-fidelity characterization.
    rows = [
        {
            "iteration": 0,
            "reported_residual": 8e-3,
            "true_residual": 8e-3,
            "relative_true_residual": 1.0,
        },
        {
            "iteration": 30,
            "reported_residual": 1e-12,
            "true_residual": 2e-3,
            "relative_true_residual": 2.5e-1,
        },
    ]
    audit = ksp.residual_fidelity_audit(rows, restart=30, ratio_threshold=1e6)
    assert audit["residual_fidelity_loss_observed"] is True
    assert audit["worst_iteration"] == 30
    assert audit["worst_at_restart_boundary"] is True
    assert audit["causal_attribution"] == "NOT_ESTABLISHED"

    print("ISSUE43_45_SHARED_CASE_IDENTITY: PASS")
    print("ISSUE45_HISTORICAL_PROVENANCE_ONLY: PASS")
    print("PARAMETERIZED_SPECIES_CONSTRAINT_SEMANTICS: PASS")
    print("ISSUE45_KSP_RESIDUAL_FIDELITY_AUDIT: PASS")
    print("ISSUE43_45_SCIENCE_REFACTOR_GUARD: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
