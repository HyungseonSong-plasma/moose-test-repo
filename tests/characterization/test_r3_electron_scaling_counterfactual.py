from experiments.R3_electron_scaling_counterfactual.cases import (
    N_E_REF,
    R3_E0_DIR,
    audit_normalized_r3_input,
    build_normalized_electron_input,
    build_normalized_r3_input,
)
from qpx_harness.moose import parameters as mp


def test_normalized_electron_case_is_o1_zero_field_diffusion() -> None:
    text = build_normalized_electron_input()
    assert mp.get_parameter(text, "Variables/n_e", "initial_condition") == "1.0"
    assert "type = FVTimeKernel" in text
    assert "type = FVDiffusion" in text
    assert "type = QPXFVElectrostaticDrift" not in text
    assert "expression = '0.0*x'" in text


def test_normalized_r3_preserves_physical_coupling_and_outputs() -> None:
    base = (R3_E0_DIR / "heavy_base.i").read_text()
    text, meta = build_normalized_r3_input(base, field_strength=0.0)

    assert mp.get_parameter(text, "Variables/n_e", "initial_condition") == "1.0"
    assert (
        mp.get_parameter(
            text,
            "FunctorMaterials/heavy_transport",
            "electron_number_density",
        )
        == "n_e_physical"
    )
    assert (
        mp.get_parameter(
            text,
            "FunctorMaterials/electron_density_physical",
            "expression",
        )
        == "'${n_e_value}*ne_hat'"
    )
    for postprocessor in ("n_e_avg", "n_e_min", "n_e_max", "n_e_inventory"):
        assert mp.get_parameter(text, f"Postprocessors/{postprocessor}", "functor") == "n_e_physical"
    for kernel in ("n_e_time", "n_e_diffusion", "n_e_drift"):
        assert mp.get_parameter(text, f"FVKernels/{kernel}", "variable") == "n_e"
    assert meta["reference_density_m3"] == N_E_REF
    assert meta["canonical_physics_checker_preserved"] is True
    assert meta["audit"]["status"] == "PASS"


def test_normalized_r3_audit_accepts_econst_variant() -> None:
    base = (R3_E0_DIR / "heavy_base.i").read_text()
    text, _ = build_normalized_r3_input(base, field_strength=0.01)
    audit = audit_normalized_r3_input(text, expected_field=0.01)
    assert audit["status"] == "PASS"
    assert not audit["failed_checks"]
