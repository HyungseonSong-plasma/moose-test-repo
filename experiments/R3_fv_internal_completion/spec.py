"""Declarative cases for one-queue FV internal completion of the R3 electron blocker."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from experiments.R3_electron_master_diagnostic.spec import FROZEN_DIFFUSION

CaseMode = Literal["solve", "gradient"]


@dataclass(frozen=True)
class CompletionCaseSpec:
    case_id: str
    mode: CaseMode
    operator: Literal["time_only", "full_internal", "orthogonal", "gradient"]
    n0: float = 1.0e16
    two_term_boundary_expansion: bool = True
    nl_abs_tol: float | None = None
    meaning: str = ""


CASES: tuple[CompletionCaseSpec, ...] = (
    CompletionCaseSpec(
        "C0_TIME_ONLY",
        "solve",
        "time_only",
        meaning="accepted time-only control on real qvt/RZ/plasma",
    ),
    CompletionCaseSpec(
        "F0_FULL_INTERNAL_N1E16",
        "solve",
        "full_internal",
        n0=1.0e16,
        meaning="nonlinear FVDiffusion internal-path anchor at physical electron-density scale",
    ),
    CompletionCaseSpec(
        "F1_FULL_INTERNAL_N1",
        "solve",
        "full_internal",
        n0=1.0,
        meaning="same nonlinear FVDiffusion internal path at O(1) state scale",
    ),
    CompletionCaseSpec(
        "F2_FULL_INTERNAL_N1_ABS1E9",
        "solve",
        "full_internal",
        n0=1.0,
        nl_abs_tol=1.0e-9,
        meaning="solver-floor confirmation with identical O(1) operator and diagnostic absolute tolerance",
    ),
    CompletionCaseSpec(
        "O0_ORTHOGONAL_N1E16",
        "solve",
        "orthogonal",
        n0=1.0e16,
        meaning="nonlinear FVOrthogonalDiffusion at physical density scale",
    ),
    CompletionCaseSpec(
        "O1_ORTHOGONAL_N1",
        "solve",
        "orthogonal",
        n0=1.0,
        meaning="nonlinear FVOrthogonalDiffusion at O(1) state scale",
    ),
    CompletionCaseSpec(
        "G0_GRAD_N1E16_TT",
        "gradient",
        "gradient",
        n0=1.0e16,
        two_term_boundary_expansion=True,
        meaning="direct AD/Real cell-gradient measurement at physical scale with two-term boundary expansion",
    ),
    CompletionCaseSpec(
        "G1_GRAD_N1_TT",
        "gradient",
        "gradient",
        n0=1.0,
        two_term_boundary_expansion=True,
        meaning="direct AD/Real cell-gradient measurement at O(1) scale with two-term boundary expansion",
    ),
    CompletionCaseSpec(
        "G2_GRAD_N1E16_ONE_TERM",
        "gradient",
        "gradient",
        n0=1.0e16,
        two_term_boundary_expansion=False,
        meaning="direct cell-gradient measurement with one-term extrapolated-boundary reconstruction",
    ),
    CompletionCaseSpec(
        "G3_GRAD_N1_ONE_TERM",
        "gradient",
        "gradient",
        n0=1.0,
        two_term_boundary_expansion=False,
        meaning="O(1) direct cell-gradient measurement with one-term boundary reconstruction",
    ),
)

CASE_BY_ID = {case.case_id: case for case in CASES}

# All Jacobian probes are predeclared now. They are deliberately few but sufficient
# to distinguish high-state conditioning from an intrinsic operator/Jacobian defect.
JACOBIAN_CASE_IDS = (
    "F0_FULL_INTERNAL_N1E16",
    "F1_FULL_INTERNAL_N1",
    "O0_ORTHOGONAL_N1E16",
)

GRADIENT_FLOOR_ABS = 1.0e-8
GRADIENT_REL_MATCH_FACTOR = 100.0
FROZEN_D = FROZEN_DIFFUSION
