"""Single-primary-owner classification for FV internal completion evidence."""
from __future__ import annotations

import math
from typing import Any, Mapping

from .spec import GRADIENT_FLOOR_ABS, GRADIENT_REL_MATCH_FACTOR


def _first_residual(cases: Mapping[str, Mapping[str, Any]], case_id: str) -> float | None:
    residuals = cases.get(case_id, {}).get("electron_residuals")
    if not isinstance(residuals, list) or not residuals:
        return None
    try:
        return float(residuals[0])
    except (TypeError, ValueError):
        return None


def _exact_zero(cases: Mapping[str, Mapping[str, Any]], case_id: str) -> bool:
    value = _first_residual(cases, case_id)
    return value == 0.0


def _nonzero(cases: Mapping[str, Mapping[str, Any]], case_id: str) -> bool:
    value = _first_residual(cases, case_id)
    return value is not None and value != 0.0


def _solver_converged(cases: Mapping[str, Mapping[str, Any]], case_id: str) -> bool:
    return cases.get(case_id, {}).get("solver_status") == "CONVERGED"


def _gradient_metric(gradients: Mapping[str, Mapping[str, Any]], case_id: str, key: str) -> float | None:
    value = gradients.get(case_id, {}).get(key)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _near_zero(value: float | None) -> bool:
    return value is not None and abs(value) <= GRADIENT_FLOOR_ABS


def _material_nonzero(value: float | None) -> bool:
    return value is not None and abs(value) > GRADIENT_FLOOR_ABS


def _within_factor(a: float | None, b: float | None, factor: float = GRADIENT_REL_MATCH_FACTOR) -> bool:
    if a is None or b is None or a == 0.0 or b == 0.0:
        return False
    ratio = abs(a / b)
    return 1.0 / factor <= ratio <= factor


def _owner(name: str, confidence: str, mechanism: str, evidence: list[str]) -> dict[str, Any]:
    return {
        "owner": name,
        "confidence": confidence,
        "mechanism": mechanism,
        "evidence": evidence,
    }


def _jacobian_secondary(jacobians: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    high = jacobians.get("F0_FULL_INTERNAL_N1E16", {}).get("status")
    low = jacobians.get("F1_FULL_INTERNAL_N1", {}).get("status")
    secondary: list[dict[str, Any]] = []
    if high == "HOLD" and low == "PASS":
        secondary.append(
            {
                "owner": "HIGH_STATE_JACOBIAN_DIAGNOSTIC_CONDITIONING",
                "status": "DISFAVORED_AS_INDEPENDENT_OWNER",
                "evidence": [
                    "F0 high-state Jacobian comparison=HOLD",
                    "F1 O(1)-state Jacobian comparison=PASS",
                ],
                "mechanism": "the Jacobian discrepancy disappears when only the absolute solved-variable scale is reduced",
            }
        )
    elif high == "HOLD" and low == "HOLD":
        secondary.append(
            {
                "owner": "FV_JACOBIAN_PATH",
                "status": "UNRESOLVED_SECONDARY_CANDIDATE",
                "evidence": [
                    "F0 high-state Jacobian comparison=HOLD",
                    "F1 O(1)-state Jacobian comparison=HOLD",
                ],
                "mechanism": "Jacobian inconsistency survives the absolute-state-scale substitution",
            }
        )
    return secondary


def classify_completion(
    cases: Mapping[str, Mapping[str, Any]],
    gradients: Mapping[str, Mapping[str, Any]],
    rz: Mapping[str, Mapping[str, Any]],
    jacobians: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Return exactly one primary owner, or null with explicit unresolved state."""
    evidence: list[str] = []
    unresolved: list[str] = []
    primary: dict[str, Any] | None = None

    if not _solver_converged(cases, "C0_TIME_ONLY"):
        return {
            "status": "HOLD_CONTROL",
            "primary_owner": None,
            "secondary_candidates": [],
            "unresolved": ["execution/control"],
            "evidence": ["C0_TIME_ONLY did not converge"],
            "geometry": "HELD_FIXED_OUT_OF_SCOPE",
            "single_primary_owner_invariant": True,
            "termination_contract": "Evidence -> Atomic Owner -> Remedy -> Verification",
        }

    full_high = _first_residual(cases, "F0_FULL_INTERNAL_N1E16")
    full_low = _first_residual(cases, "F1_FULL_INTERNAL_N1")
    orth_high = _first_residual(cases, "O0_ORTHOGONAL_N1E16")
    orth_low = _first_residual(cases, "O1_ORTHOGONAL_N1")

    evidence.extend(
        [
            f"F0 full/high residual={full_high!r}",
            f"F1 full/O(1) residual={full_low!r}",
            f"O0 orthogonal/high residual={orth_high!r}",
            f"O1 orthogonal/O(1) residual={orth_low!r}",
        ]
    )

    # First discriminator: if the direct cell-difference-only nonlinear FV path
    # itself creates a constant-state residual, the owner lies below Green-Gauss.
    if _nonzero(cases, "O0_ORTHOGONAL_N1E16") or _nonzero(cases, "O1_ORTHOGONAL_N1"):
        primary = _owner(
            "FV_ORTHOGONAL_VALUE_DIFFERENCE_OR_ASSEMBLY",
            "ISOLATED_OWNER_CLASS",
            "constant-state failure is already present in FVOrthogonalDiffusion, which bypasses Green-Gauss/non-orthogonal reconstruction and uses only neighbor-minus-element values over dCN",
            [
                f"O0 residual={orth_high!r}",
                f"O1 residual={orth_low!r}",
                "FVOrthogonalDiffusion is the minimal prebuilt nonlinear cell-difference path",
            ],
        )

    # Main expected branch: orthogonal-only is exact while the full nonlinear
    # FVDiffusion path is nonzero. Then directly inspect cell Green-Gauss gradients.
    elif _exact_zero(cases, "O0_ORTHOGONAL_N1E16") and _nonzero(cases, "F0_FULL_INTERNAL_N1E16"):
        g0_ad = _gradient_metric(gradients, "G0_GRAD_N1E16_TT", "ad_max")
        g0_real = _gradient_metric(gradients, "G0_GRAD_N1E16_TT", "real_max")
        g0_ad_int = _gradient_metric(gradients, "G0_GRAD_N1E16_TT", "ad_interior_max")
        g0_real_int = _gradient_metric(gradients, "G0_GRAD_N1E16_TT", "real_interior_max")
        g2_ad = _gradient_metric(gradients, "G2_GRAD_N1E16_ONE_TERM", "ad_max")
        g2_real = _gradient_metric(gradients, "G2_GRAD_N1E16_ONE_TERM", "real_max")
        evidence.extend(
            [
                f"G0 two-term AD max={g0_ad!r}",
                f"G0 two-term Real max={g0_real!r}",
                f"G0 two-term AD interior max={g0_ad_int!r}",
                f"G0 two-term Real interior max={g0_real_int!r}",
                f"G2 one-term AD max={g2_ad!r}",
                f"G2 one-term Real max={g2_real!r}",
            ]
        )

        if _material_nonzero(g0_ad_int) and _near_zero(g0_real_int):
            primary = _owner(
                "FV_AD_GREEN_GAUSS_CONSTANT_PRESERVATION",
                "ISOLATED",
                "the same interior constant state has a material AD Green-Gauss gradient while the Real-functor gradient remains at numerical zero",
                [
                    f"G0 AD interior={g0_ad_int:.12g}",
                    f"G0 Real interior={g0_real_int:.12g}",
                    "O0 orthogonal-only residual=0",
                    "F0 full FVDiffusion residual!=0",
                ],
            )
        elif _material_nonzero(g0_ad_int) and _material_nonzero(g0_real_int):
            qpx_norm = max(abs(g0_ad_int), abs(g0_real_int)) / 1.0e16
            rz_norm = None
            for key in ("N1E16", "n1e16", "high"):
                candidate = rz.get(key, {}).get("normalized_max_abs_final_naive")
                if candidate is not None:
                    rz_norm = float(candidate)
                    break
            if rz_norm is None:
                candidate = rz.get("N1E16", {}).get("normalized_max_abs_final_fsum")
                if candidate is not None:
                    rz_norm = float(candidate)
            if _within_factor(qpx_norm, rz_norm):
                primary = _owner(
                    "FV_RZ_GREEN_GAUSS_CONSTANT_CANCELLATION",
                    "ISOLATED",
                    "direct QPX cell-gradient evidence and an independent reconstruction of the pinned RZ Green-Gauss face-sum minus n/r arithmetic exhibit comparable normalized constant-state floors on the same qvt mesh",
                    [
                        f"QPX normalized interior gradient={qpx_norm:.12g}",
                        f"offline pinned-RZ normalized floor={rz_norm:.12g}",
                        "O0 orthogonal-only residual=0",
                        "F0 full FVDiffusion residual!=0",
                    ],
                )
            else:
                primary = _owner(
                    "FV_GREEN_GAUSS_CELL_RECONSTRUCTION",
                    "FAVORED",
                    "the constant-state cell gradient is already nonzero on interior cells in both AD and Real paths, but the offline RZ arithmetic magnitude does not yet uniquely account for it",
                    [
                        f"G0 AD interior={g0_ad_int:.12g}",
                        f"G0 Real interior={g0_real_int:.12g}",
                        f"offline normalized RZ floor={rz_norm!r}",
                    ],
                )
        elif (_material_nonzero(g0_ad) or _material_nonzero(g0_real)) and _near_zero(g0_ad_int) and _near_zero(g0_real_int):
            if _near_zero(g2_ad) and _near_zero(g2_real):
                primary = _owner(
                    "FV_GREEN_GAUSS_TWO_TERM_BOUNDARY_RECONSTRUCTION",
                    "ISOLATED",
                    "the direct Green-Gauss gradient floor is confined to boundary-adjacent cells and disappears when extrapolated boundaries use one-term reconstruction",
                    [
                        "G0 two-term all-cell gradient nonzero",
                        "G0 interior gradient near zero",
                        "G2 one-term all-cell gradient near zero",
                    ],
                )
            else:
                primary = _owner(
                    "FV_GREEN_GAUSS_BOUNDARY_RECONSTRUCTION",
                    "FAVORED",
                    "the Green-Gauss floor is confined to boundary-adjacent cells but survives the two-term to one-term boundary substitution",
                    [
                        "G0 all-cell gradient nonzero",
                        "G0 interior gradient near zero",
                        f"G2 one-term AD={g2_ad!r}",
                        f"G2 one-term Real={g2_real!r}",
                    ],
                )
        elif _near_zero(g0_ad) and _near_zero(g0_real):
            primary = _owner(
                "FV_FACE_NONORTHOGONAL_STATE_OR_ASSEMBLY",
                "FAVORED",
                "cell Green-Gauss gradients are numerically zero while full FVDiffusion remains nonzero and FVOrthogonalDiffusion is exact; the remaining active owner is the face-level non-orthogonal gradient/assembly path",
                [
                    "O0 orthogonal-only residual=0",
                    "F0 full residual!=0",
                    f"G0 AD max={g0_ad!r}",
                    f"G0 Real max={g0_real!r}",
                ],
            )
        else:
            unresolved.append("cell-gradient measurement did not match a terminal predeclared branch")

    elif _exact_zero(cases, "F0_FULL_INTERNAL_N1E16"):
        evidence.append("F0 full internal FVDiffusion is exactly zero")
    else:
        unresolved.append("full/orthogonal residual evidence incomplete or non-terminal")

    if _solver_converged(cases, "F2_FULL_INTERNAL_N1_ABS1E9"):
        evidence.append("F2 O(1) full operator converges when diagnostic nl_abs_tol=1e-9")

    secondary = _jacobian_secondary(jacobians)
    if primary is not None:
        status = "ISOLATED" if primary["confidence"] == "ISOLATED" else "FAVORED"
    elif not unresolved and _exact_zero(cases, "F0_FULL_INTERNAL_N1E16"):
        status = "OPERATOR_PASS"
    else:
        status = "UNRESOLVED"

    return {
        "status": status,
        "primary_owner": primary,
        "secondary_candidates": secondary,
        "unresolved": unresolved,
        "evidence": evidence,
        "geometry": "HELD_FIXED_OUT_OF_SCOPE",
        "single_primary_owner_invariant": True,
        "termination_contract": "Evidence -> Atomic Owner -> Remedy -> Verification",
    }
