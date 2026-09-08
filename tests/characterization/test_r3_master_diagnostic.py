from experiments.R3_electron_master_diagnostic.classify import classify_matrix
from experiments.R3_electron_master_diagnostic.spec import CHEAP_CASES


def _matrix(**values):
    return {
        spec.case_id: {
            "status": "PASS" if values.get(spec.case_id, True) else "FAIL",
            "passed": values.get(spec.case_id, True),
        }
        for spec in CHEAP_CASES
    }


def _runtime(
    cases,
    case_id,
    *,
    passed,
    residual,
    returncode=None,
    checker_pass=None,
    failure=None,
):
    if returncode is None:
        returncode = 0 if passed else 1
    if checker_pass is None:
        checker_pass = passed
    cases[case_id].update(
        {
            "status": "PASS" if passed else "FAIL",
            "passed": passed,
            "returncode": returncode,
            "timed_out": False,
            "electron_residuals": [residual] if residual is not None else [],
            "checker": {"pass": checker_pass},
            "failure_signature": {"signature": failure, "iterations": None},
        }
    )


def test_required_anchors_are_only_established_issue94_paths():
    required = {spec.case_id for spec in CHEAP_CASES if spec.kind == "required"}
    assert required == {
        "A0_TIME_ONLY",
        "A1_QPX_BASELINE",
        "A2_LITERAL_BASE",
        "A3_GENERIC_AD_BASE",
    }


def test_qpx_lookup_transition_maps_owner_and_proxy():
    cases = _matrix(A1_QPX_BASELINE=False, E2_QPX_NO_BOUNDARY=False, Q3_QPX_ALL_LITERAL=False)
    result = classify_matrix(cases)
    assert [item["owner"] for item in result["owners"]] == ["QPX_LOOKUP"]
    assert result["owners"][0]["remedy_proxy_case"] == "A3_GENERIC_AD_BASE"
    assert result["geometry"] == "HELD_FIXED_OUT_OF_SCOPE"
    assert "A1_QPX_BASELINE" in result["selected_jacobian_cases"]


def test_boundary_reconstruction_transition_precedes_broad_fvdiffusion_owner():
    cases = _matrix(
        A2_LITERAL_BASE=False,
        B0_TWO_TERM_FALSE=False,
        B1_TWO_TERM_TRUE=True,
    )
    result = classify_matrix(cases)
    assert result["owners"][0]["owner"] == "BOUNDARY_RECONSTRUCTION"
    assert result["owners"][0]["remedy_proxy_case"] == "B1_TWO_TERM_TRUE"


def test_constant_preservation_floor_uses_operator_and_solver_evidence_separately():
    cases = _matrix(
        A2_LITERAL_BASE=False,
        B0_TWO_TERM_FALSE=False,
        B1_TWO_TERM_TRUE=False,
        B2_VAR_FACE_SKEW=False,
        B3_DIFF_VAR_SKEW=False,
        B4_BOTH_SKEW=False,
        B5_CACHE_FALSE=False,
        B6_INSFV=False,
        E0_LITERAL_NO_BOUNDARY=False,
    )
    _runtime(cases, "M0_LITERAL_N1_RAW", passed=False, residual=1.0e-10, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "M1_LITERAL_N1E4_RAW", passed=False, residual=1.0e-6, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "M2_LITERAL_N1E8_RAW", passed=False, residual=1.0e-2, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "M3_LITERAL_N1E12_RAW", passed=False, residual=1.0e2, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "M4_LITERAL_N1E14_RAW", passed=False, residual=1.0e4, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "M5_LITERAL_N1_ABS1E9", passed=True, residual=1.0e-10)
    _runtime(cases, "K0_LITERAL_D0_RAW", passed=True, residual=0.0)
    _runtime(cases, "K1_LITERAL_D1_RAW", passed=False, residual=24.23, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "K2_LITERAL_D1E2_RAW", passed=False, residual=2423.0, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "K3_LITERAL_D1E4_RAW", passed=False, residual=242300.0, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "K4_LITERAL_DFROZEN_RAW", passed=False, residual=999999.0, failure="DIVERGED_LINE_SEARCH")

    result = classify_matrix(cases)
    assert [item["owner"] for item in result["owners"]] == ["FV_CONSTANT_PRESERVATION_FLOOR"]
    assert result["case_statuses"]["M0_LITERAL_N1_RAW"]["operator_status"] == "NUMERICAL_FLOOR_CANDIDATE"
    assert result["case_statuses"]["M0_LITERAL_N1_RAW"]["solver_status"] == "DIVERGED_LINE_SEARCH"
    assert result["case_statuses"]["M5_LITERAL_N1_ABS1E9"]["solver_status"] == "CONVERGED"
    assert 0.85 <= result["trend_evidence"]["magnitude_slope"] <= 1.15
    assert 0.85 <= result["trend_evidence"]["diffusion_slope"] <= 1.15
    assert "M0_LITERAL_N1_RAW" in result["selected_jacobian_cases"]
    assert "A2_LITERAL_BASE" in result["selected_jacobian_cases"]


def test_nonorthogonal_reference_can_refine_floor_owner_without_becoming_proxy():
    cases = _matrix(
        A2_LITERAL_BASE=False,
        B0_TWO_TERM_FALSE=False,
        B1_TWO_TERM_TRUE=False,
        B2_VAR_FACE_SKEW=False,
        B3_DIFF_VAR_SKEW=False,
        B4_BOTH_SKEW=False,
        B5_CACHE_FALSE=False,
        B6_INSFV=False,
        E0_LITERAL_NO_BOUNDARY=False,
        O1_LINEAR_NONORTHOGONAL_REF=False,
    )
    _runtime(cases, "M0_LITERAL_N1_RAW", passed=False, residual=1.0e-10, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "M1_LITERAL_N1E4_RAW", passed=False, residual=1.0e-6, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "M2_LITERAL_N1E8_RAW", passed=False, residual=1.0e-2, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "M3_LITERAL_N1E12_RAW", passed=False, residual=1.0e2, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "M4_LITERAL_N1E14_RAW", passed=False, residual=1.0e4, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "M5_LITERAL_N1_ABS1E9", passed=True, residual=1.0e-10)
    _runtime(cases, "K0_LITERAL_D0_RAW", passed=True, residual=0.0)
    _runtime(cases, "K1_LITERAL_D1_RAW", passed=False, residual=24.23, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "K2_LITERAL_D1E2_RAW", passed=False, residual=2423.0, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "K3_LITERAL_D1E4_RAW", passed=False, residual=242300.0, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "K4_LITERAL_DFROZEN_RAW", passed=False, residual=999999.0, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "O0_LINEAR_ORTHOGONAL_REF", passed=True, residual=None)
    _runtime(cases, "O1_LINEAR_NONORTHOGONAL_REF", passed=False, residual=None, failure=None)

    result = classify_matrix(cases)
    assert [item["owner"] for item in result["owners"]] == ["FV_NONORTHOGONAL_CONSTANT_PRESERVATION"]
    assert result["owners"][0]["remedy_proxy_case"] is None


def test_broad_fvdiffusion_owner_requires_material_o1_residual_and_zero_diffusion_exact_zero():
    cases = _matrix(
        A2_LITERAL_BASE=False,
        B0_TWO_TERM_FALSE=False,
        B1_TWO_TERM_TRUE=False,
        B2_VAR_FACE_SKEW=False,
        B3_DIFF_VAR_SKEW=False,
        B4_BOTH_SKEW=False,
        B5_CACHE_FALSE=False,
        B6_INSFV=False,
        E0_LITERAL_NO_BOUNDARY=False,
    )
    _runtime(cases, "M0_LITERAL_N1_RAW", passed=False, residual=1.0, failure="DIVERGED_LINE_SEARCH")
    _runtime(cases, "K0_LITERAL_D0_RAW", passed=True, residual=0.0)
    result = classify_matrix(cases)
    assert [item["owner"] for item in result["owners"]] == ["FVDIFFUSION_INTERNAL_ASSEMBLY"]


def test_control_failure_holds_scientific_attribution():
    result = classify_matrix(_matrix(A0_TIME_ONLY=False))
    assert result["status"] == "HOLD"
    assert result["class"] == "CONTROL_REGRESSION"
    assert result["owners"] == []
