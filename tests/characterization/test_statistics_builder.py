"""Characterization of canonical statistics construction boundaries."""

from __future__ import annotations

import pytest

from qpx_harness.analysis.statistics_builder import (
    build_accuracy_stats,
    build_common_stats,
    build_convergence_stats,
    build_simulation_stats,
)


def test_statistics_builder_preserves_characterized_mapping_contract() -> None:
    performance = {
        "run_id": "run-1",
        "experiment_id": "exp-1",
        "case_id": "case-1",
        "environment": {"hostname": "host", "platform": "linux", "python": "3.12", "mpi_ranks": 2, "threads": 4, "logical_cpu_count": 16, "qpx_realpath": "/opt/solver-executable", "moose": "moose-v", "petsc": "petsc-v"},
        "problem": {"nodes": 10, "elements": 8, "dofs": 12, "variables": ["u", "v"], "species": ["O2", "O"]},
        "work": {"nonlinear_iterations": 3, "linear_iterations": 9, "residual_evaluations": 5, "jacobian_evaluations": 2},
        "performance": {"wall_seconds": 1.25, "max_memory_mb": 128.0, "perfgraph": {"max_memory_this_rank_mb": 128.0, "max_memory_per_rank_mb": [128.0, 96.0], "nodes": [{"name": "app", "parent": None, "level": 0, "self_seconds": 0.25, "num_calls": 1}]}, "petsc": {"rows": [{"Event Name": "SNESJacobianEval", "Rank": 0, "Count": 2, "Time": 0.4}]}},
        "validation": {"status": "P2_PASS_P3_PASS", "p2_returncode": 0, "p3_returncode": 0},
        "execution_contract": {"decision": "must remain outside Stats"},
        "scientific_decision": "must remain outside Stats",
    }
    convergence = build_convergence_stats(
        work=performance["work"],
        linear_terminations=[{"converged": False, "reason": "DIVERGED_BREAKDOWN", "iterations": 30}],
        nonlinear_terminations=[{"converged": True, "reason": "CONVERGED_FNORM_ABS", "iterations": 2}],
        ksp_view={"ksp_type": "gmres", "restart": 30, "pc_type": "lu"},
        true_residuals=[{"iteration": 0, "reported_residual": 1.0, "true_residual": 0.8, "relative_true_residual": 0.4}],
        variable_residual_blocks=[{"u": 1.0e-4, "v": 2.0e-4}],
        scaling_factor_blocks=[{"u": 2.0, "v": 4.0}],
        trajectory={"physical_rows": 5, "first_time": 1.0e-13, "final_time": 5.0e-13, "actual_dt_min": 1.0e-13, "actual_dt_max": 1.0e-13},
    )
    accuracy = build_accuracy_stats(
        jacobian_comparisons=[{"relative_frobenius_error": 5.0e-11, "absolute_frobenius_error": 1.0e-8}],
        reference_comparisons=[{"key": "Dmix_A_O2", "candidate": 1.01, "legacy": 1.00, "relative_error": 0.01}],
        invariants=[{"name": "electron_inventory", "observed_value": 10.0, "reference_value": 10.0, "relative_error": 0.0}],
        matrix_comparisons=[{"name": "thresholded_jacobian_difference", "threshold": 1.0e-6, "section_observed": True, "structural_entry_count": 2, "nonzero_thresholded_entry_count": 1, "mapped_entry_count": 1, "thresholded_l2_difference": 0.25, "entries": [{"row": 1, "col": 2, "value": 0.25, "row_variable": "u", "col_variable": "v"}], "blocks": {"u->v": {"row_variable": "u", "col_variable": "v", "count": 1, "sum_squared_difference": 0.0625, "max_abs_difference": 0.25, "l2_difference": 0.25}}}],
    )
    stats = build_simulation_stats(performance, convergence=convergence, accuracy=accuracy)

    assert stats.common.case_id == "case-1"
    assert stats.common.wall_time_seconds == 1.25
    assert stats.common.environment is not None and stats.common.environment.logical_cpu_count == 16
    assert stats.efficiency is not None and stats.efficiency.jacobian_evaluations == 2
    assert any(timing.source == "petsc_log" and timing.total_seconds == 0.4 for timing in stats.efficiency.timings)
    assert len(stats.efficiency.memories) == 3
    assert stats.convergence is not None and stats.convergence.terminations[0].converged is False
    assert stats.convergence.solver is not None and stats.convergence.solver.linear_restart == 30
    assert len(stats.convergence.residuals) == 5 and len(stats.convergence.scaling_factors) == 2
    assert stats.accuracy is not None and stats.accuracy.matrix_errors[0].error.relative_error == 5.0e-11
    assert stats.accuracy.reference_errors[0].observed_value == 1.01
    thresholded = stats.accuracy.matrix_errors[1]
    assert thresholded.blocks[0].sum_squared_difference == 0.0625
    assert thresholded.entries[0].difference == 0.25
    assert not hasattr(stats, "execution_contract")
    assert not hasattr(stats, "scientific_decision")
    with pytest.raises(ValueError):
        build_common_stats({"run_id": "missing-case"})
