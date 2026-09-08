import json

from experiments.R3_electron_master_diagnostic.cases import build_case_text, stage_master_case
from experiments.R3_electron_master_diagnostic.spec import CHEAP_CASES, FROZEN_NEUTRAL_DENSITY


CASES = {spec.case_id: spec for spec in CHEAP_CASES}


def test_all_master_cases_construct_from_current_issue94_inputs():
    for spec in CHEAP_CASES:
        text = build_case_text(spec)
        assert f"R3 master diagnostic: {spec.case_id}" in text
        assert "[Variables]" in text
        if spec.base == "LINEAR_REF":
            assert "[LinearFVKernels]" in text
            assert "type = LinearFVDiffusion" in text
        else:
            assert "[FVKernels]" in text
            assert "diag_electron_diffusion_min" in text
            assert "diag_electron_diffusion_max" in text


def test_generic_transport_keeps_neutral_density_observable_contract_valid():
    text = build_case_text(CASES["A3_GENERIC_AD_BASE"])
    assert "prop_names = 'electron_mobility electron_diffusion neutral_number_density'" in text
    assert repr(FROZEN_NEUTRAL_DENSITY) in text
    assert "[neutral_number_density_avg]" in text


def test_magnitude_case_updates_input_and_expected_n0(tmp_path):
    spec = CASES["M0_LITERAL_N1_RAW"]
    target = tmp_path / spec.case_id
    stage_master_case(spec, target)
    text = (target / "input.i").read_text()
    expected = json.loads((target / "expected.json").read_text())
    assert "initial_condition = 1.0" in text
    assert "automatic_scaling = false" in text
    assert expected["n0"] == 1.0


def test_solver_floor_probe_sets_diagnostic_absolute_tolerance():
    text = build_case_text(CASES["M5_LITERAL_N1_ABS1E9"])
    assert "initial_condition = 1.0" in text
    assert "nl_abs_tol = 1e-9" in text
    assert "automatic_scaling = false" in text


def test_zero_diffusion_conditioning_case_keeps_kernel_but_sets_zero_coefficient():
    text = build_case_text(CASES["K0_LITERAL_D0_RAW"])
    assert "  [diffusion]\n" in text
    assert "coeff = 0.0" in text


def test_linear_reference_pair_changes_only_nonorthogonal_switch_semantically():
    orth = build_case_text(CASES["O0_LINEAR_ORTHOGONAL_REF"])
    nonorth = build_case_text(CASES["O1_LINEAR_NONORTHOGONAL_REF"])
    assert "type = MooseLinearVariableFVReal" in orth
    assert "type = LinearFVTimeDerivative" in orth
    assert "use_nonorthogonal_correction = false" in orth
    assert "use_nonorthogonal_correction = true" in nonorth
    assert "linear_sys_names = 'electron_diag_sys'" in orth
    assert "[neutral_number_density_avg]" in orth
    assert "[electron_mobility_avg]" in orth
    assert "[electron_diffusion_avg]" in orth
