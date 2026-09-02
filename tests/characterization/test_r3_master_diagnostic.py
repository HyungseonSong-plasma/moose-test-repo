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


def test_state_magnitude_transition_blocks_premature_internal_assembly_owner():
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
        M0_LITERAL_N1_RAW=True,
        K0_LITERAL_D0_RAW=True,
    )
    result = classify_matrix(cases)
    owners = [item["owner"] for item in result["owners"]]
    assert owners == ["STATE_MAGNITUDE_CONDITIONING"]
    assert "FVDIFFUSION_INTERNAL_ASSEMBLY" not in owners
    assert result["owners"][0]["remedy_proxy_case"] is None
    assert "M0_LITERAL_N1_RAW" in result["selected_jacobian_cases"]


def test_broad_fvdiffusion_owner_requires_o1_failure_and_zero_diffusion_pass():
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
        M0_LITERAL_N1_RAW=False,
        M1_LITERAL_N1E4_RAW=False,
        M2_LITERAL_N1E8_RAW=False,
        M3_LITERAL_N1E12_RAW=False,
        M4_LITERAL_N1E14_RAW=False,
        K0_LITERAL_D0_RAW=True,
    )
    result = classify_matrix(cases)
    assert [item["owner"] for item in result["owners"]] == ["FVDIFFUSION_INTERNAL_ASSEMBLY"]


def test_control_failure_holds_scientific_attribution():
    result = classify_matrix(_matrix(A0_TIME_ONLY=False))
    assert result["status"] == "HOLD"
    assert result["class"] == "CONTROL_REGRESSION"
    assert result["owners"] == []
