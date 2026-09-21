"""Evidence-driven classification for the R3 one-shot diagnostic matrix."""
from __future__ import annotations

import math
from typing import Any, Mapping

from .execution_status import operator_status, solver_status
from .spec import CHEAP_CASES, FROZEN_DIFFUSION, REMEDY_MAP

CASE_SPECS = {spec.case_id: spec for spec in CHEAP_CASES}
MAGNITUDE_CASES = (
    "M0_LITERAL_N1_RAW",
    "M1_LITERAL_N1E4_RAW",
    "M2_LITERAL_N1E8_RAW",
    "M3_LITERAL_N1E12_RAW",
    "M4_LITERAL_N1E14_RAW",
)
MAGNITUDE_POINTS = (
    ("M0_LITERAL_N1_RAW", 1.0),
    ("M1_LITERAL_N1E4_RAW", 1.0e4),
    ("M2_LITERAL_N1E8_RAW", 1.0e8),
    ("M3_LITERAL_N1E12_RAW", 1.0e12),
    ("M4_LITERAL_N1E14_RAW", 1.0e14),
    ("K4_LITERAL_DFROZEN_RAW", 1.0e16),
)
DIFFUSION_STRENGTH_CASES = (
    "K0_LITERAL_D0_RAW",
    "K1_LITERAL_D1_RAW",
    "K2_LITERAL_D1E2_RAW",
    "K3_LITERAL_D1E4_RAW",
    "K4_LITERAL_DFROZEN_RAW",
)
DIFFUSION_POINTS = (
    ("K1_LITERAL_D1_RAW", 1.0),
    ("K2_LITERAL_D1E2_RAW", 1.0e2),
    ("K3_LITERAL_D1E4_RAW", 1.0e4),
    ("K4_LITERAL_DFROZEN_RAW", FROZEN_DIFFUSION),
)


def _passed(cases: Mapping[str, Mapping[str, Any]], case_id: str) -> bool:
    return bool(cases.get(case_id, {}).get("passed"))


def _supported(cases: Mapping[str, Mapping[str, Any]], case_id: str) -> bool:
    return cases.get(case_id, {}).get("status") not in {
        None,
        "CONSTRUCTION_FAIL",
        "P2_FAIL",
        "P3_SETUP_FAIL",
        "SKIPPED_UNSUPPORTED",
        "NOT_RUN",
    }


def _transition(cases: Mapping[str, Mapping[str, Any]], fail_id: str, pass_id: str) -> bool:
    return _supported(cases, fail_id) and not _passed(cases, fail_id) and _passed(cases, pass_id)


def _owner(owner: str, *, evidence: list[str], proxy: str | None, mechanism: str) -> dict[str, Any]:
    return {
        "owner": owner,
        "mechanism": mechanism,
        "evidence": evidence,
        "remedy": REMEDY_MAP.get(owner),
        "remedy_proxy_case": proxy,
    }


def _first_residual(cases: Mapping[str, Mapping[str, Any]], case_id: str) -> float | None:
    values = cases.get(case_id, {}).get("electron_residuals")
    if not isinstance(values, list) or not values:
        return None
    try:
        return float(values[0])
    except (TypeError, ValueError):
        return None


def _log_slope(cases: Mapping[str, Mapping[str, Any]], points: tuple[tuple[str, float], ...]) -> float | None:
    xy: list[tuple[float, float]] = []
    for case_id, scale in points:
        residual = _first_residual(cases, case_id)
        if residual is None or residual == 0.0 or scale <= 0.0:
            continue
        xy.append((math.log10(scale), math.log10(abs(residual))))
    if len(xy) < 3:
        return None
    xbar = sum(x for x, _ in xy) / len(xy)
    ybar = sum(y for _, y in xy) / len(xy)
    denom = sum((x - xbar) ** 2 for x, _ in xy)
    if denom == 0.0:
        return None
    return sum((x - xbar) * (y - ybar) for x, y in xy) / denom


def _near_one(value: float | None) -> bool:
    return value is not None and 0.85 <= value <= 1.15


def _case_statuses(cases: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    for case_id, case in cases.items():
        spec = CASE_SPECS.get(case_id)
        if spec is None:
            continue
        residuals = case.get("electron_residuals")
        if not isinstance(residuals, list):
            residuals = []
        checker = case.get("checker")
        if not isinstance(checker, dict):
            checker = {}
        failure = case.get("failure_signature")
        if not isinstance(failure, dict):
            failure = {"signature": None}
        returncode = case.get("returncode")
        timed_out = bool(case.get("timed_out"))
        if not isinstance(returncode, int):
            statuses[case_id] = {
                "operator_status": "NOT_RUN",
                "solver_status": "NOT_RUN",
                "jacobian_status": case.get("jacobian_status", "NOT_RUN"),
            }
            continue
        statuses[case_id] = {
            "operator_status": operator_status(
                spec,
                electron_residuals=[float(value) for value in residuals],
                checker=checker,
            ),
            "solver_status": solver_status(
                returncode=returncode,
                timed_out=timed_out,
                failure=failure,
                checker=checker,
            ),
            "jacobian_status": case.get("jacobian_status", "NOT_RUN"),
        }
    return statuses


def select_jacobian_cases(
    cases: Mapping[str, Mapping[str, Any]],
    owners: list[dict[str, Any]],
    case_statuses: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    selected: list[str] = []
    names = {item["owner"] for item in owners}

    # The O(1) density case must be tested even when the nonlinear solve labels it
    # FAIL: a small constant-preservation floor and a solver divergence are separate facts.
    if case_statuses.get("M0_LITERAL_N1_RAW", {}).get("operator_status") == "NUMERICAL_FLOOR_CANDIDATE":
        selected.extend(["A2_LITERAL_BASE", "M0_LITERAL_N1_RAW"])

    if names & {"FVDIFFUSION_INTERNAL_ASSEMBLY", "FV_CONSTANT_PRESERVATION_FLOOR", "FV_NONORTHOGONAL_CONSTANT_PRESERVATION"}:
        selected.append("A2_LITERAL_BASE")
    if "STATE_MAGNITUDE_CONDITIONING" in names:
        selected.extend(["A2_LITERAL_BASE", "M0_LITERAL_N1_RAW"])
    if names & {"BOUNDARY_RECONSTRUCTION", "VARIABLE_INTERPOLATION", "VARIABLE_CLASS"}:
        selected.append("A2_LITERAL_BASE")
        for candidate in ("B1_TWO_TERM_TRUE", "B2_VAR_FACE_SKEW", "B3_DIFF_VAR_SKEW", "B6_INSFV"):
            if _passed(cases, candidate):
                selected.append(candidate)
                break
    if "GENERIC_FUNCTOR_AD" in names:
        selected.extend(["A2_LITERAL_BASE", "A3_GENERIC_AD_BASE"])
    if names & {"QPX_LOOKUP", "QPX_BOUNDARY_FACEARG"}:
        selected.extend(["A3_GENERIC_AD_BASE", "A1_QPX_BASELINE"])
    if not selected and _passed(cases, "A1_QPX_BASELINE"):
        selected.append("A1_QPX_BASELINE")
    return list(dict.fromkeys(selected))


def classify_matrix(cases: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    owners: list[dict[str, Any]] = []
    notes: list[str] = []
    unresolved: list[str] = []
    case_statuses = _case_statuses(cases)
    magnitude_slope = _log_slope(cases, MAGNITUDE_POINTS)
    diffusion_slope = _log_slope(cases, DIFFUSION_POINTS)

    if not _passed(cases, "A0_TIME_ONLY"):
        return {
            "status": "HOLD",
            "class": "CONTROL_REGRESSION",
            "owners": [],
            "notes": ["time-only control did not pass; scientific attribution is blocked"],
            "selected_jacobian_cases": [],
            "case_statuses": case_statuses,
            "trend_evidence": {"magnitude_slope": magnitude_slope, "diffusion_slope": diffusion_slope},
            "geometry": "HELD_FIXED_OUT_OF_SCOPE",
            "unresolved_active_owner": ["execution/control"],
        }

    literal = _passed(cases, "A2_LITERAL_BASE")
    generic_ad = _passed(cases, "A3_GENERIC_AD_BASE")
    qpx = _passed(cases, "A1_QPX_BASELINE")

    if not literal:
        if _transition(cases, "B0_TWO_TERM_FALSE", "B1_TWO_TERM_TRUE"):
            owners.append(_owner(
                "BOUNDARY_RECONSTRUCTION",
                evidence=["B0_TWO_TERM_FALSE=FAIL", "B1_TWO_TERM_TRUE=PASS"],
                proxy="B1_TWO_TERM_TRUE",
                mechanism="boundary reconstruction policy changes the constant-state FAIL->PASS transition",
            ))
        else:
            interp_pass = next((cid for cid in (
                "B2_VAR_FACE_SKEW", "B3_DIFF_VAR_SKEW", "B4_BOTH_SKEW", "B5_CACHE_FALSE"
            ) if _passed(cases, cid)), None)
            if interp_pass and not _passed(cases, "B1_TWO_TERM_TRUE"):
                owners.append(_owner(
                    "VARIABLE_INTERPOLATION",
                    evidence=["B1_TWO_TERM_TRUE=FAIL", f"{interp_pass}=PASS"],
                    proxy=interp_pass,
                    mechanism="face/gradient interpolation or cache policy controls the transition",
                ))
            elif _transition(cases, "B1_TWO_TERM_TRUE", "B6_INSFV"):
                owners.append(_owner(
                    "VARIABLE_CLASS",
                    evidence=["B1_TWO_TERM_TRUE=FAIL", "B6_INSFV=PASS"],
                    proxy="B6_INSFV",
                    mechanism="INSFV subclass semantics change the outcome after matched two-term reconstruction",
                ))

        if not owners:
            m0_operator = case_statuses.get("M0_LITERAL_N1_RAW", {}).get("operator_status")
            m5_solver = case_statuses.get("M5_LITERAL_N1_ABS1E9", {}).get("solver_status")
            k0_operator = case_statuses.get("K0_LITERAL_D0_RAW", {}).get("operator_status")
            floor_pattern = (
                m0_operator == "NUMERICAL_FLOOR_CANDIDATE"
                and m5_solver == "CONVERGED"
                and k0_operator == "EXACT_ZERO"
                and _near_one(magnitude_slope)
                and _near_one(diffusion_slope)
            )
            if floor_pattern:
                evidence = [
                    "M0_LITERAL_N1_RAW operator=NUMERICAL_FLOOR_CANDIDATE",
                    "M5_LITERAL_N1_ABS1E9 solver=CONVERGED",
                    "K0_LITERAL_D0_RAW operator=EXACT_ZERO",
                    f"raw residual magnitude slope vs n_e={magnitude_slope:.6g}",
                    f"raw residual diffusion slope vs D_e={diffusion_slope:.6g}",
                ]
                o0 = case_statuses.get("O0_LINEAR_ORTHOGONAL_REF", {})
                o1 = case_statuses.get("O1_LINEAR_NONORTHOGONAL_REF", {})
                if o0.get("solver_status") == "CONVERGED" and o1.get("solver_status") != "CONVERGED" and _supported(cases, "O1_LINEAR_NONORTHOGONAL_REF"):
                    evidence.extend([
                        "same-mesh LinearFVDiffusion orthogonal reference=CONVERGED",
                        f"same-mesh LinearFVDiffusion non-orthogonal reference={o1.get('solver_status')}",
                    ])
                    owners.append(_owner(
                        "FV_NONORTHOGONAL_CONSTANT_PRESERVATION",
                        evidence=evidence,
                        proxy=None,
                        mechanism="the dimensional constant-state residual floor scales approximately as n_e*D_e, is accepted at O(1) with a diagnostic absolute tolerance, vanishes for D=0, and an independent same-mesh LinearFVDiffusion reference changes behavior when non-orthogonal correction is enabled",
                    ))
                else:
                    if _supported(cases, "O0_LINEAR_ORTHOGONAL_REF") and _supported(cases, "O1_LINEAR_NONORTHOGONAL_REF"):
                        notes.append(
                            "LinearFVDiffusion orthogonal/non-orthogonal reference did not provide a FAIL->PASS transition; it is supporting context only and does not exonerate the nonlinear gradient path."
                        )
                    owners.append(_owner(
                        "FV_CONSTANT_PRESERVATION_FLOOR",
                        evidence=evidence,
                        proxy=None,
                        mechanism="the zero-gradient literal-D path exhibits a small O(1) residual floor whose raw magnitude scales approximately linearly with both n_e and D_e; the floor becomes solver-acceptable under a diagnostic absolute tolerance, favoring dimensional amplification of a finite-precision FV gradient/reconstruction floor over a coefficient-provider defect",
                    ))

        if not owners:
            b_cases = [
                "B0_TWO_TERM_FALSE", "B1_TWO_TERM_TRUE", "B2_VAR_FACE_SKEW",
                "B3_DIFF_VAR_SKEW", "B4_BOTH_SKEW", "B5_CACHE_FALSE", "B6_INSFV",
            ]
            m0_operator = case_statuses.get("M0_LITERAL_N1_RAW", {}).get("operator_status")
            zero_d_ok = case_statuses.get("K0_LITERAL_D0_RAW", {}).get("operator_status") == "EXACT_ZERO"
            if (
                all(_supported(cases, cid) and not _passed(cases, cid) for cid in b_cases)
                and _supported(cases, "E0_LITERAL_NO_BOUNDARY")
                and not _passed(cases, "E0_LITERAL_NO_BOUNDARY")
                and m0_operator == "NONZERO_RESIDUAL"
                and zero_d_ok
            ):
                owners.append(_owner(
                    "FVDIFFUSION_INTERNAL_ASSEMBLY",
                    evidence=[
                        "literal D fails",
                        "all variable/reconstruction discriminators fail",
                        "boundary-excluded literal case fails",
                        "O(1) constant-state literal-D residual remains materially nonzero",
                        "zero-coefficient FVDiffusion case is exactly zero",
                    ],
                    proxy=None,
                    mechanism="constant-state diffusion failure survives coefficient-provider, variable/reconstruction, named-boundary, and absolute-state-scale substitutions while disappearing at zero diffusion coefficient",
                ))
            else:
                unresolved.append("literal FVDiffusion/variable/reconstruction/constant-preservation branch")

    elif not generic_ad:
        evidence = ["A2_LITERAL_BASE=PASS", "A3_GENERIC_AD_BASE=FAIL"]
        if _passed(cases, "C2_GENERIC_NONAD"):
            evidence.append("C2_GENERIC_NONAD=PASS")
            mechanism = "failure first appears when the generic coefficient path becomes AD"
        else:
            mechanism = "failure first appears on the generic functor/material coefficient path"
        owners.append(_owner("GENERIC_FUNCTOR_AD", evidence=evidence, proxy="A2_LITERAL_BASE", mechanism=mechanism))

    elif not qpx:
        if _passed(cases, "E2_QPX_NO_BOUNDARY"):
            owners.append(_owner(
                "QPX_BOUNDARY_FACEARG",
                evidence=["A3_GENERIC_AD_BASE=PASS", "A1_QPX_BASELINE=FAIL", "E2_QPX_NO_BOUNDARY=PASS"],
                proxy="E2_QPX_NO_BOUNDARY",
                mechanism="QPX-owned coefficient fails only when named boundary FaceArg evaluation is active",
            ))
        else:
            q_evidence = ["A3_GENERIC_AD_BASE=PASS", "A1_QPX_BASELINE=FAIL"]
            if _passed(cases, "Q3_QPX_ALL_LITERAL"):
                q_evidence.append("Q3_QPX_ALL_LITERAL=PASS")
                mechanism = "freezing all QPX lookup inputs removes the failure; input Functor delivery is favored"
            elif _supported(cases, "Q3_QPX_ALL_LITERAL") and not _passed(cases, "Q3_QPX_ALL_LITERAL"):
                q_evidence.append("Q3_QPX_ALL_LITERAL=FAIL")
                mechanism = "failure survives literal lookup inputs; QPX material value/context/derivative path remains"
            else:
                mechanism = "QPX lookup path is the first provider-specific failing transition"
            owners.append(_owner("QPX_LOOKUP", evidence=q_evidence, proxy="A3_GENERIC_AD_BASE", mechanism=mechanism))

    else:
        notes.append("literal, generic AD, and QPX residual paths all pass in this runtime")

    # Solver ownership is a fallback only. Do not append it beside an operator owner.
    if not owners and not qpx and _passed(cases, "S0_QPX_SCALING_OFF"):
        qpx_case = cases.get("A1_QPX_BASELINE", {})
        if qpx_case.get("coefficient_contract_pass") is True and qpx_case.get("jacobian_status") == "PASS":
            owners.append(_owner(
                "SOLVER_SCALING",
                evidence=["A1_QPX_BASELINE=FAIL", "S0_QPX_SCALING_OFF=PASS", "coefficient contract=PASS", "Jacobian=PASS"],
                proxy="S0_QPX_SCALING_OFF",
                mechanism="operator evidence is correct while nonlinear scaling changes the solve outcome",
            ))

    selected = select_jacobian_cases(cases, owners, case_statuses)
    status = "ISOLATED" if owners and not unresolved else ("UNRESOLVED" if unresolved else "RESIDUAL_MATRIX_PASS")
    return {
        "status": status,
        "class": "R3_MASTER_DIAGNOSTIC",
        "owners": owners,
        "notes": notes,
        "selected_jacobian_cases": selected,
        "case_statuses": case_statuses,
        "trend_evidence": {
            "magnitude_slope": magnitude_slope,
            "diffusion_slope": diffusion_slope,
            "expected_floor_relation": "raw_residual ~ n_e * D_e when constant-preservation floor dominates",
        },
        "geometry": "HELD_FIXED_OUT_OF_SCOPE",
        "unresolved_active_owner": unresolved,
    }
