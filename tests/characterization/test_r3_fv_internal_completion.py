import math

from experiments.Issue93_r3_electron_isolation.prepare import ELECTRON_REFERENCE_CASE
from experiments.R3_fv_internal_completion.cases import build_case_text
from experiments.R3_fv_internal_completion.classify import classify_completion
from experiments.R3_fv_internal_completion.rz_decomposition import decompose_rz_constant_state
from experiments.R3_fv_internal_completion.spec import CASES, JACOBIAN_CASE_IDS


def test_completion_matrix_prebuilds_all_remaining_fv_layers():
    assert set(JACOBIAN_CASE_IDS) == {
        "F0_FULL_INTERNAL_N1E16",
        "F1_FULL_INTERNAL_N1",
        "O0_ORTHOGONAL_N1E16",
    }
    for spec in CASES:
        text = build_case_text(spec)
        assert f"R3 FV internal completion: {spec.case_id}" in text
        assert "coord_type = RZ" in text
        assert "file = 'qvt.msh'" in text
        if spec.operator == "full_internal":
            assert "type = FVDiffusion" in text
            assert "boundaries_to_avoid = 'inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover plasma_wafer plasma_focus_ring'" in text
            assert "automatic_scaling = false" in text
        elif spec.operator == "orthogonal":
            assert "type = FVOrthogonalDiffusion" in text
            assert "type = ADGenericConstantMaterial" in text
            assert "diag_orthogonal_D" in text
            material_block = text.split("[diag_orthogonal_diffusivity]", 1)[1].split("[]", 1)[0]
            assert "block = plasma" in material_block
            # The accepted reference [Materials] contract is retained; the
            # diagnostic diffusivity does not need to cover unrelated mesh blocks.
            assert "[vacuum]" in text
            assert "[cover]" in text
            assert "[electrode]" in text
            assert "[wafer]" in text
            assert "[focus_ring]" in text
            assert "[plasma]" in text
        elif spec.operator == "gradient":
            assert "type = ADFunctorElementalGradientAux" in text
            assert "type = FunctorElementalGradientAux" in text
            assert "type = ElementValueSampler" in text
            assert "solve = false" in text
            expected = "two_term_boundary_expansion = true" if spec.two_term_boundary_expansion else "two_term_boundary_expansion = false"
            assert expected in text


def test_rz_reproducer_uses_real_qvt_and_preserves_normalized_floor_order():
    mesh = ELECTRON_REFERENCE_CASE / "qvt.msh"
    low = decompose_rz_constant_state(mesh, n0=1.0)
    high = decompose_rz_constant_state(mesh, n0=1.0e16)
    assert low["plasma_element_count"] > 0
    assert low["interior_element_count"] > 0
    assert low["interior_element_count"] == high["interior_element_count"]
    # The reproducer deliberately exposes finite-precision cancellation, so the
    # normalized floor need not be bitwise scale-invariant. It must remain in the
    # same narrow order-of-magnitude band when n0 changes by sixteen decades.
    for key in ("normalized_max_abs_final_naive", "normalized_max_abs_final_fsum"):
        assert math.isfinite(low[key])
        assert math.isfinite(high[key])
        assert low[key] > 0.0
        ratio = high[key] / low[key]
        assert 0.99 <= ratio <= 1.01


def _base_cases():
    return {
        spec.case_id: {
            "status": "PASS",
            "passed": True,
            "solver_status": "CONVERGED",
            "electron_residuals": [0.0],
        }
        for spec in CASES
    }


def test_classifier_isolates_rz_green_gauss_and_keeps_jacobian_secondary():
    cases = _base_cases()
    cases["F0_FULL_INTERNAL_N1E16"].update(
        status="FAIL", passed=False, solver_status="DIVERGED_LINE_SEARCH", electron_residuals=[9.5e5]
    )
    cases["F1_FULL_INTERNAL_N1"].update(
        status="FAIL", passed=False, solver_status="DIVERGED_LINE_SEARCH", electron_residuals=[8.0e-11]
    )
    cases["F2_FULL_INTERNAL_N1_ABS1E9"].update(
        status="PASS", passed=True, solver_status="CONVERGED", electron_residuals=[8.0e-11]
    )
    gradients = {
        "G0_GRAD_N1E16_TT": {
            "ad_max": 4.0,
            "real_max": 3.0,
            "ad_interior_max": 2.0,
            "real_interior_max": 1.5,
        },
        "G2_GRAD_N1E16_ONE_TERM": {
            "ad_max": 4.0,
            "real_max": 3.0,
            "ad_interior_max": 2.0,
            "real_interior_max": 1.5,
        },
    }
    rz = {"N1E16": {"normalized_max_abs_final_naive": 2.0e-16}}
    jacobians = {
        "F0_FULL_INTERNAL_N1E16": {"status": "HOLD"},
        "F1_FULL_INTERNAL_N1": {"status": "PASS"},
        "O0_ORTHOGONAL_N1E16": {"status": "PASS"},
    }
    result = classify_completion(cases, gradients, rz, jacobians)
    assert result["status"] == "ISOLATED"
    assert result["single_primary_owner_invariant"] is True
    assert result["primary_owner"]["owner"] == "FV_RZ_GREEN_GAUSS_CONSTANT_CANCELLATION"
    assert len(result["secondary_candidates"]) == 1
    assert result["secondary_candidates"][0]["owner"] == "HIGH_STATE_JACOBIAN_DIAGNOSTIC_CONDITIONING"
    assert result["secondary_candidates"][0]["status"] == "DISFAVORED_AS_INDEPENDENT_OWNER"


def test_classifier_routes_zero_cell_gradient_to_face_nonorthogonal_path():
    cases = _base_cases()
    cases["F0_FULL_INTERNAL_N1E16"].update(
        status="FAIL", passed=False, solver_status="DIVERGED_LINE_SEARCH", electron_residuals=[9.5e5]
    )
    gradients = {
        "G0_GRAD_N1E16_TT": {
            "ad_max": 0.0,
            "real_max": 0.0,
            "ad_interior_max": 0.0,
            "real_interior_max": 0.0,
        },
        "G2_GRAD_N1E16_ONE_TERM": {
            "ad_max": 0.0,
            "real_max": 0.0,
            "ad_interior_max": 0.0,
            "real_interior_max": 0.0,
        },
    }
    result = classify_completion(cases, gradients, {}, {})
    assert result["status"] == "FAVORED"
    assert result["primary_owner"]["owner"] == "FV_FACE_NONORTHOGONAL_STATE_OR_ASSEMBLY"
    assert result["unresolved"] == []


def test_orthogonal_nonzero_preempts_green_gauss_owner():
    cases = _base_cases()
    cases["F0_FULL_INTERNAL_N1E16"].update(
        status="FAIL", passed=False, solver_status="DIVERGED_LINE_SEARCH", electron_residuals=[9.5e5]
    )
    cases["O0_ORTHOGONAL_N1E16"].update(
        status="FAIL", passed=False, solver_status="DIVERGED_LINE_SEARCH", electron_residuals=[1.0]
    )
    result = classify_completion(cases, {}, {}, {})
    assert result["primary_owner"]["owner"] == "FV_ORTHOGONAL_VALUE_DIFFERENCE_OR_ASSEMBLY"
    assert len([result["primary_owner"]]) == 1
