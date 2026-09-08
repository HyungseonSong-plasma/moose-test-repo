"""Dependency-free canonical simulation evaluation data contracts for QPX harness.

Stats represent normalized evaluation information only. Metric computation,
generic diagnostics, execution-contract evaluation, and scientific decisions live
outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProblemStats:
    """Normalized problem-size and variable identity facts."""

    nodes: int | None = None
    elements: int | None = None
    dofs: int | None = None
    variables: tuple[str, ...] = ()
    species: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EnvironmentStats:
    """Normalized execution-environment and framework identity facts."""

    hostname: str | None = None
    platform: str | None = None
    system: str | None = None
    machine: str | None = None
    processor: str | None = None
    python_version: str | None = None
    mpi_ranks: int | None = None
    threads: int | None = None
    qpx_realpath: str | None = None
    moose_version: str | None = None
    libmesh_version: str | None = None
    petsc_version: str | None = None
    slepc_version: str | None = None
    logical_cpu_count: int | None = None


@dataclass(frozen=True, slots=True)
class CommonStats:
    """Run identity and whole-execution facts shared by all evaluation axes."""

    case_id: str
    run_id: str | None = None
    experiment_id: str | None = None
    backend: str | None = None
    return_code: int | None = None
    wall_time_seconds: float | None = None
    timestamp_iso: str | None = None
    problem: ProblemStats | None = None
    environment: EnvironmentStats | None = None


@dataclass(frozen=True, slots=True)
class TimingStats:
    """One normalized timing/event record without bottleneck interpretation."""

    name: str
    source: str | None = None
    self_seconds: float | None = None
    inclusive_seconds: float | None = None
    call_count: int | None = None
    path: tuple[str, ...] = ()
    rank: int | None = None
    total_seconds: float | None = None
    parent: str | None = None
    level: int | None = None


@dataclass(frozen=True, slots=True)
class MemoryStats:
    """One normalized memory observation preserving the producer unit."""

    kind: str
    value: float
    unit: str
    source: str | None = None
    rank: int | None = None


@dataclass(frozen=True, slots=True)
class EfficiencyStats:
    """Computational-work and resource-use facts excluding whole-run wall time."""

    peak_rss_bytes: int | None = None
    residual_evaluations: int | None = None
    jacobian_evaluations: int | None = None
    timings: tuple[TimingStats, ...] = ()
    memories: tuple[MemoryStats, ...] = ()


@dataclass(frozen=True, slots=True)
class SolverTerminationStats:
    """One observed solver termination reason for one solve instance."""

    solver: str
    reason: str
    solve_index: int | None = None
    iteration_count: int | None = None
    converged: bool | None = None


@dataclass(frozen=True, slots=True)
class ResidualSample:
    """One normalized residual observation."""

    value: float
    kind: str
    solve_index: int | None = None
    iteration: int | None = None
    step_index: int | None = None
    variable: str | None = None
    norm_type: str | None = None


@dataclass(frozen=True, slots=True)
class SolverConfigStats:
    """Observed solver configuration relevant to generic convergence analysis."""

    nonlinear_solver: str | None = None
    linear_solver: str | None = None
    preconditioner: str | None = None
    linear_restart: int | None = None
    linear_max_iterations: int | None = None
    nonlinear_max_iterations: int | None = None
    linear_relative_tolerance: float | None = None
    linear_absolute_tolerance: float | None = None
    nonlinear_relative_tolerance: float | None = None
    nonlinear_absolute_tolerance: float | None = None


@dataclass(frozen=True, slots=True)
class ScalingFactorStats:
    """One observed MOOSE automatic-scaling factor."""

    variable: str
    value: float
    block_index: int | None = None
    step_index: int | None = None


@dataclass(frozen=True, slots=True)
class ConvergenceStats:
    """Solver-trajectory facts without hypothesis or scientific PASS/FAIL policy."""

    linear_iterations: int | None = None
    nonlinear_iterations: int | None = None
    physical_step_count: int | None = None
    first_time_seconds: float | None = None
    final_time_seconds: float | None = None
    actual_dt_min_seconds: float | None = None
    actual_dt_max_seconds: float | None = None
    solver: SolverConfigStats | None = None
    terminations: tuple[SolverTerminationStats, ...] = ()
    residuals: tuple[ResidualSample, ...] = ()
    scaling_factors: tuple[ScalingFactorStats, ...] = ()


@dataclass(frozen=True, slots=True)
class ErrorStats:
    """Reusable scalar error representation."""

    absolute_error: float | None = None
    relative_error: float | None = None
    norm_type: str | None = None
    reference_id: str | None = None


@dataclass(frozen=True, slots=True)
class FieldErrorStats:
    """Error information associated with one physical or numerical field."""

    field_name: str
    error: ErrorStats


@dataclass(frozen=True, slots=True)
class InvariantErrorStats:
    """Deviation from a conservation law, invariant, or algebraic identity."""

    name: str
    error: ErrorStats
    observed_value: float | None = None
    reference_value: float | None = None


@dataclass(frozen=True, slots=True)
class ReferenceErrorStats:
    """Scalar candidate/reference comparison not tied to one simulation field."""

    name: str
    error: ErrorStats
    observed_value: float | None = None
    reference_value: float | None = None


@dataclass(frozen=True, slots=True)
class MatrixEntryErrorStats:
    """One matrix/Jacobian difference entry with optional variable ownership."""

    row: int
    col: int
    difference: float
    row_variable: str | None = None
    col_variable: str | None = None


@dataclass(frozen=True, slots=True)
class MatrixBlockErrorStats:
    """Localized matrix-difference facts for one row/column owner block."""

    row_variable: str
    col_variable: str
    entry_count: int
    l2_difference: float | None = None
    max_abs_difference: float | None = None
    energy_fraction: float | None = None
    sum_squared_difference: float | None = None


@dataclass(frozen=True, slots=True)
class MatrixErrorStats:
    """Matrix/Jacobian comparison facts without acceptance policy."""

    name: str
    error: ErrorStats
    threshold: float | None = None
    structural_entry_count: int | None = None
    nonzero_thresholded_entry_count: int | None = None
    thresholded_l2_difference: float | None = None
    blocks: tuple[MatrixBlockErrorStats, ...] = ()
    comparison_index: int | None = None
    entries: tuple[MatrixEntryErrorStats, ...] = ()
    section_observed: bool | None = None
    mapped_entry_count: int | None = None


@dataclass(frozen=True, slots=True)
class AccuracyStats:
    """Reference, field, invariant, and matrix error facts."""

    field_errors: tuple[FieldErrorStats, ...] = ()
    invariant_errors: tuple[InvariantErrorStats, ...] = ()
    matrix_errors: tuple[MatrixErrorStats, ...] = ()
    reference_errors: tuple[ReferenceErrorStats, ...] = ()


@dataclass(frozen=True, slots=True)
class SimulationStats:
    """Canonical normalized evaluation information for one simulation run."""

    common: CommonStats
    efficiency: EfficiencyStats | None = None
    convergence: ConvergenceStats | None = None
    accuracy: AccuracyStats | None = None
