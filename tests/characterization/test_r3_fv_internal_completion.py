import inspect
import math

from experiments.Issue93_r3_electron_isolation.prepare import ELECTRON_REFERENCE_CASE
from experiments.R3_fv_internal_completion.cases import build_case_text
from experiments.R3_fv_internal_completion.classify import classify_completion
from experiments.R3_fv_internal_completion.face_interpolation_audit import (
    audit_constant_face_interpolation,
    moose_constant_linear_interpolation,
)
from experiments.R3_fv_internal_completion.run import _jacobian_case
from experiments.R3_fv_internal_completion.rz_decomposition import decompose_rz_constant_state
from experiments.R3_fv_internal_completion.spec import CASES, JACOBIAN_CASE_IDS


def test_completion_matrix_prebuilds_all_remaining_fv_layers():
    assert set(JACOBIAN_CASE_IDS) == {
        "F0_FULL_INTERNAL_N1E16",
        "F1_FULL_INTERNAL_N1",
        "O0_ORTHOGONAL_N1E16",
    }
    case_ids = {spec.case_id for spec in CASES}
    assert "P0_GRADIENT_PINNED_STYLE" in case_ids
    assert "P1_GRADIENT_INITIAL_VARIANT" in case_ids

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
            assert "[vacuum]" in text
            assert "[cover]" in text
            assert "[electrode]" in text
            assert "[wafer]" in text
            assert "[focus_ring]" in text
            assert "[plasma]" in text
        elif spec.mode == "gradient":
            assert "type = ADFunctorElementalGradientAux" in text
            assert "type = FunctorElementalGradientAux" in text
            assert "type = VectorVariableComponentAux" in text
            assert "type = ElementValueSampler" in text
            assert "solve = false" in text
            assert "[Executioner]\n  type = Steady\n[]" in text
            assert "[FVKernels]\n" not in text
            assert "type = FVTimeKernel" not in text
            assert "type = FVDiffusion" not in text
            assert "[FunctorMaterials]\n" not in text
            assert "type = QPXElectronTransportLookupMaterial" not in text
            assert "[Postprocessors]\n" not in text
            expected = "two_term_boundary_expansion = true" if spec.two_term_boundary_expansion else "two_term_boundary_expansion = false"
            assert expected in text
            assert "[vacuum]" in text
            assert "[plasma]" in text
            if spec.operator == "gradient_initial":
                assert "execute_on = INITIAL" in text
            else:
                assert "execute_on = INITIAL" not in text


def test_rz_reproducer_uses_real_qvt_and_preserves_normalized_floor_order():
    mesh = ELECTRON_REFERENCE_CASE / "qvt.msh"
    low = decompose_rz_constant_state(mesh, n0=1.0)
    high = decompose_rz_constant_state(mesh, n0=1.0e16)
    # Accepted qvt input has rz_coord_axis=Y, which is the symmetry axis.
    # MOOSE therefore uses X/component 0 as the radial coordinate.
    assert low["radial_axis"] == 0
    assert high["radial_axis"] == 0
    assert low["symmetry_axis"] == 1
    assert high["symmetry_axis"] == 1
    assert low["plasma_element_count"] > 0
    assert low["interior_element_count"] > 0
    assert low["interior_element_count"] == high["interior_element_count"]
    for key in ("normalized_max_abs_final_naive", "normalized_max_abs_final_fsum"):
        assert math.isfinite(low[key])
        assert math.isfinite(high[key])
        assert low[key] > 0.0
        ratio = high[key] / low[key]
        assert 0.95 <= ratio <= 1.05


def test_constant_face_interpolation_audit_runs_on_real_qvt_without_owner_assumption():
    mesh = ELECTRON_REFERENCE_CASE / "qvt.msh"
    low = audit_constant_face_interpolation(mesh, n0=1.0)
    high = audit_constant_face_interpolation(mesh, n0=1.0e16)

    assert set(low["plasma_gmsh_element_types"]) <= {2, 3}
    assert low["plasma_gmsh_element_types"]
    assert low["radial_axis"] == high["radial_axis"] == 0
    assert low["symmetry_axis"] == high["symmetry_axis"] == 1
    assert low["interior_element_count"] == high["interior_element_count"] > 0
    assert low["face_evaluation_count"] == high["face_evaluation_count"] > 0
    for result in (low, high):
        assert result["interpretation"] == "EVIDENCE_ONLY_NO_OWNER_ASSIGNMENT"
        assert result["gc_outside_unit_count"] >= 0
        assert result["nonzero_face_delta_count"] >= 0
        assert math.isfinite(result["max_gc_overshoot"])
        assert math.isfinite(result["max_abs_face_delta"])
        assert math.isfinite(result["max_abs_final_gradient"])
        assert math.isfinite(result["normalized_max_abs_final_gradient"])


def test_equal_value_weighted_interpolation_can_have_roundoff_when_gc_extrapolates():
    n0 = 1.0e16
    gc = -0.6441943115068004
    face = moose_constant_linear_interpolation(n0, gc)
    assert face != n0
    assert math.isfinite(face - n0)


def test_jacobian_probe_is_one_shot_and_does_not_dump_full_matrix():
    source = inspect.getsource(_jacobian_case)
    assert 'Executioner/abort_on_solve_fail=true' in source
    assert '-snes_test_jacobian' in source
    assert '-snes_test_jacobian_view' not in source


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


def _probe_gradients(*, initial_pass: bool = True):
    result = {
        "P0_GRADIENT_PINNED_STYLE": {
            "status": "PASS",
            "ad_max": 0.0,
            "real_max": 0.0,
            "ad_interior_max": 0.0,
            "real_interior_max": 0.0,
        }
    }
    if initial_pass:
        result["P1_GRADIENT_INITIAL_VARIANT"] = {
            "status": "PASS",
            "ad_max": 0.0,
            "real_max": 0.0,
            "ad_interior_max": 0.0,
            "real_interior_max": 0.0,
        }
    return result


def test_classifier_isolates_green_gauss_cell_gradient_without_rz_over_attribution():
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
    gradients = _probe_gradients()
    gradients.update(
        {
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
    )
    rz = {"N1E16": {"normalized_max_abs_final_naive": 2.0e-16}}
    jacobians = {
        "F0_FULL_INTERNAL_N1E16": {"status": "HOLD"},
        "F1_FULL_INTERNAL_N1": {"status": "PASS"},
        "O0_ORTHOGONAL_N1E16": {"status": "PASS"},
    }
    result = classify_completion(cases, gradients, rz, jacobians)
    assert result["status"] == "ISOLATED"
    assert result["single_primary_owner_invariant"] is True
    assert result["primary_owner"]["owner"] == "FV_GREEN_GAUSS_CELL_GRADIENT_CONSTANT_PRESERVATION"
    assert "RZ-specific versus general Green-Gauss arithmetic" in result["unresolved"][0]
    assert len(result["secondary_candidates"]) == 1
    assert result["secondary_candidates"][0]["owner"] == "HIGH_STATE_JACOBIAN_DIAGNOSTIC_CONDITIONING"
    assert result["secondary_candidates"][0]["status"] == "DISFAVORED_AS_INDEPENDENT_OWNER"
    assert result["operational_findings"][0]["scientific_gate"] == "OPEN"


def test_classifier_routes_zero_cell_gradient_to_face_nonorthogonal_path():
    cases = _base_cases()
    cases["F0_FULL_INTERNAL_N1E16"].update(
        status="FAIL", passed=False, solver_status="DIVERGED_LINE_SEARCH", electron_residuals=[9.5e5]
    )
    gradients = _probe_gradients()
    gradients.update(
        {
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
    )
    result = classify_completion(cases, gradients, {}, {})
    assert result["status"] == "FAVORED"
    assert result["primary_owner"]["owner"] == "FV_FACE_NONORTHOGONAL_STATE_OR_ASSEMBLY"
    assert result["unresolved"] == []


def test_pinned_gradient_probe_failure_closes_scientific_gradient_gate():
    cases = _base_cases()
    cases["F0_FULL_INTERNAL_N1E16"].update(
        status="FAIL", passed=False, solver_status="DIVERGED_LINE_SEARCH", electron_residuals=[9.5e5]
    )
    cases["P0_GRADIENT_PINNED_STYLE"].update(status="P2_FAIL", passed=False)
    result = classify_completion(cases, {}, {}, {})
    assert result["status"] == "HOLD_GRADIENT_PROBE"
    assert result["primary_owner"] is None
    assert result["unresolved"] == ["gradient_probe_execution_contract"]
    assert result["operational_findings"][0]["scientific_gate"] == "CLOSED"


def test_initial_schedule_failure_does_not_block_pinned_style_science():
    cases = _base_cases()
    cases["F0_FULL_INTERNAL_N1E16"].update(
        status="FAIL", passed=False, solver_status="DIVERGED_LINE_SEARCH", electron_residuals=[9.5e5]
    )
    cases["P1_GRADIENT_INITIAL_VARIANT"].update(status="P2_FAIL", passed=False)
    gradients = _probe_gradients(initial_pass=False)
    gradients.update(
        {
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
    )
    result = classify_completion(cases, gradients, {}, {})
    assert result["status"] == "FAVORED"
    assert result["primary_owner"]["owner"] == "FV_FACE_NONORTHOGONAL_STATE_OR_ASSEMBLY"
    initial = next(item for item in result["operational_findings"] if item["case_id"] == "P1_GRADIENT_INITIAL_VARIANT")
    assert initial["status"] == "UNSUPPORTED_OR_FAILED_COUNTERFACTUAL"
    assert initial["scientific_gate"] == "NOT_USED_FOR_G_CASES"


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
