"""Evidence-driven classification for the R3 one-shot diagnostic matrix."""
from __future__ import annotations

from typing import Any, Mapping

from .spec import REMEDY_MAP


def _passed(cases: Mapping[str, Mapping[str, Any]], case_id: str) -> bool:
    return bool(cases.get(case_id, {}).get("passed"))


def _supported(cases: Mapping[str, Mapping[str, Any]], case_id: str) -> bool:
    return cases.get(case_id, {}).get("status") not in {
        None,
        "CONSTRUCTION_FAIL",
        "P2_FAIL",
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


def select_jacobian_cases(cases: Mapping[str, Mapping[str, Any]], owners: list[dict[str, Any]]) -> list[str]:
    selected: list[str] = []
    names = {item["owner"] for item in owners}
    if "FVDIFFUSION_INTERNAL_ASSEMBLY" in names:
        selected.append("A2_LITERAL_BASE")
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

    if not _passed(cases, "A0_TIME_ONLY"):
        return {
            "status": "HOLD",
            "class": "CONTROL_REGRESSION",
            "owners": [],
            "notes": ["time-only control did not pass; scientific attribution is blocked"],
            "selected_jacobian_cases": [],
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
            else:
                b_cases = [
                    "B0_TWO_TERM_FALSE", "B1_TWO_TERM_TRUE", "B2_VAR_FACE_SKEW",
                    "B3_DIFF_VAR_SKEW", "B4_BOTH_SKEW", "B5_CACHE_FALSE", "B6_INSFV",
                ]
                if all(_supported(cases, cid) and not _passed(cases, cid) for cid in b_cases) and not _passed(cases, "E0_LITERAL_NO_BOUNDARY"):
                    owners.append(_owner(
                        "FVDIFFUSION_INTERNAL_ASSEMBLY",
                        evidence=["literal D fails", "all variable/reconstruction discriminators fail", "boundary-excluded literal case fails"],
                        proxy=None,
                        mechanism="constant-state diffusion failure survives coefficient-provider, variable/reconstruction, and named-boundary substitutions",
                    ))
                else:
                    unresolved.append("literal FVDiffusion/variable/reconstruction branch")

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

    if not qpx and _passed(cases, "S0_QPX_SCALING_OFF"):
        qpx_case = cases.get("A1_QPX_BASELINE", {})
        if qpx_case.get("coefficient_contract_pass") is True and qpx_case.get("jacobian_status") == "PASS":
            owners.append(_owner(
                "SOLVER_SCALING",
                evidence=["A1_QPX_BASELINE=FAIL", "S0_QPX_SCALING_OFF=PASS", "coefficient contract=PASS", "Jacobian=PASS"],
                proxy="S0_QPX_SCALING_OFF",
                mechanism="operator evidence is correct while nonlinear scaling changes the solve outcome",
            ))

    selected = select_jacobian_cases(cases, owners)
    status = "ISOLATED" if owners and not unresolved else ("UNRESOLVED" if unresolved else "RESIDUAL_MATRIX_PASS")
    return {
        "status": status,
        "class": "R3_MASTER_DIAGNOSTIC",
        "owners": owners,
        "notes": notes,
        "selected_jacobian_cases": selected,
        "geometry": "HELD_FIXED_OUT_OF_SCOPE",
        "unresolved_active_owner": unresolved,
    }
