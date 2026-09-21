from pathlib import Path
from types import SimpleNamespace

from experiments.R3_electron_scaling_counterfactual import run as scaling_run
from experiments.R3_electron_scaling_counterfactual.cases import (
    N_E_REF,
    R3_E0_DIR,
    audit_normalized_r3_input,
    build_normalized_electron_input,
    build_normalized_r3_input,
)
from experiments.historical_recipe_support.issue91_r3 import build_r3_input
from physics_harness.adapters.moose import parameters as mp


def test_normalized_electron_case_is_o1_zero_field_diffusion() -> None:
    text = build_normalized_electron_input()
    assert mp.get_parameter(text, "Variables/n_e", "initial_condition") == "1.0"
    assert mp.get_parameter(text, "Executioner", "nl_abs_tol") == "1.0e-14"
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


def test_scaling_wrapper_is_identical_to_canonical_r3_after_promotion() -> None:
    base = (R3_E0_DIR / "heavy_base.i").read_text()
    canonical_text, canonical_meta = build_r3_input(base, field_strength=0.01)
    verified_text, verified_meta = build_normalized_r3_input(base, field_strength=0.01)

    assert verified_text == canonical_text
    assert canonical_text.count("[electron_density_physical]") == 1
    assert canonical_meta["electron_solver_unknown"] == "n_e == n_hat"
    assert verified_meta["counterfactual"] == "CANONICAL_ELECTRON_DENSITY_O1_REPRESENTATION_VERIFICATION"


def test_normalized_r3_audit_accepts_econst_variant() -> None:
    base = (R3_E0_DIR / "heavy_base.i").read_text()
    text, _ = build_normalized_r3_input(base, field_strength=0.01)
    audit = audit_normalized_r3_input(text, expected_field=0.01)
    assert audit["status"] == "PASS"
    assert not audit["failed_checks"]


def test_r3_checker_resolves_paths_before_changing_cwd(tmp_path, monkeypatch) -> None:
    case_dir = tmp_path / "relative" / "case"
    case_dir.mkdir(parents=True)
    (case_dir / "input_out.csv").write_text("time\n1e-8\n")
    (case_dir / "expected.json").write_text("{}\n")
    captured: dict[str, object] = {}

    def fake_run(command, *, cwd, text, capture_output, check):
        captured["command"] = command
        captured["cwd"] = cwd
        return SimpleNamespace(returncode=0, stdout="PASS\n", stderr="")

    monkeypatch.setattr(scaling_run.subprocess, "run", fake_run)
    result = scaling_run._check_r3(Path(case_dir))

    assert result["pass"] is True
    command = captured["command"]
    assert isinstance(command, list)
    assert Path(command[1]).is_absolute()
    assert Path(command[2]).is_absolute()
    assert Path(command[3]).is_absolute()
    assert Path(captured["cwd"]).is_absolute()


def test_jacobian_probe_forces_evaluation_below_runtime_absolute_floor() -> None:
    args = scaling_run._jacobian_extra_args()
    assert "Executioner/nl_abs_tol=1.0e-30" in args
    assert "-snes_test_jacobian" in args
