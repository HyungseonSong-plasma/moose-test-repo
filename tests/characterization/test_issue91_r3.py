from __future__ import annotations

import csv
import json
from pathlib import Path

from experiments.Issue91_real_qvt_r3 import run as issue91_run
from experiments.historical_recipe_support.issue91_r3 import audit_r3_input, build_r3_input
from qpx_harness.adapters.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
CASE_ROOT = ROOT / "experiments/Issue91_real_qvt_r3"


def _base() -> str:
    return (CASE_ROOT / "r3_econst/heavy_base.i").read_text()


def test_issue91_assets_are_self_contained() -> None:
    for name in ("r3_e0", "r3_econst"):
        case = CASE_ROOT / name
        for required in (
            "heavy_base.i",
            "qvt.msh",
            "transport_data.txt",
            "electron_moments.txt",
            "prepare.py",
            "check.py",
            "expected.json",
            "test.json",
        ):
            assert (case / required).is_file(), (name, required)


def test_issue91_prepare_scripts_are_cwd_independent() -> None:
    for name in ("r3_e0", "r3_econst"):
        source = (CASE_ROOT / name / "prepare.py").read_text()
        assert "CASE_DIR = Path(__file__).resolve().parent" in source
        assert '(CASE_DIR / "heavy_base.i").read_text()' in source
        assert '(CASE_DIR / "input.i").write_text(text)' in source
        assert '(CASE_DIR / "prepare_evidence.json").write_text(' in source
        assert 'Path("heavy_base.i")' not in source


def test_issue91_temporal_checker_uses_positive_time_normalized_rows() -> None:
    for name in ("r3_e0", "r3_econst"):
        cfg = json.loads((CASE_ROOT / name / "test.json").read_text())
        expected = json.loads((CASE_ROOT / name / "expected.json").read_text())
        assert cfg["checker_args"] == ["input_out.physical.csv", "expected.json"]
        assert "input_out.csv" not in cfg["checker_args"]
        assert len(cfg["temporal_csv"]) == 1
        spec = cfg["temporal_csv"][0]
        assert spec["source"] == "input_out.csv"
        assert spec["physical"] == "input_out.physical.csv"
        assert spec["initial_row_policy"] == "exclude_observation"
        # The acceptance contract remains dimensional even though the solver
        # unknown is now the O(1) normalized electron density.
        assert expected["n0"] == 1.0e16


def test_r3_econst_composition_is_structurally_valid() -> None:
    text, meta = build_r3_input(_base(), field_strength=0.01)
    audit = audit_r3_input(text, expected_field=0.01)
    assert audit["status"] == "PASS"
    assert meta["poisson_enabled"] is False
    assert meta["electron_initial_condition"] == "normalized_1.0"
    assert meta["electron_solver_unknown"] == "n_e == n_hat"
    assert meta["electron_reference_density_m3"] == 1.0e16
    assert meta["electron_physical_density"] == "n_e_physical == n_e_value*n_e"
    assert meta["electron_pressure"] == "p"
    assert meta["electron_gas_temperature"] == "T_g"
    assert meta["common_timestep"] == 1.0e-8
    assert mp.get_parameter(text, "Variables/n_e", "initial_condition") == "1.0"
    assert (
        mp.get_parameter(
            text,
            "FunctorMaterials/electron_density_physical",
            "expression",
        )
        == "'${n_e_value}*ne_hat'"
    )
    assert "n_e_ic_profile" not in text
    assert "[domain_volume]" in text


def test_r3_zero_field_changes_only_declared_field_axis() -> None:
    base = _base()
    zero, zero_meta = build_r3_input(base, field_strength=0.0)
    field, field_meta = build_r3_input(base, field_strength=0.01)
    assert audit_r3_input(zero, expected_field=0.0)["status"] == "PASS"
    assert audit_r3_input(field, expected_field=0.01)["status"] == "PASS"
    assert zero != field
    assert zero_meta["field_strength"] == 0.0
    assert field_meta["field_strength"] == 0.01


def test_r3_preserves_heavy_transport_and_uses_physical_electron_bridge() -> None:
    text, _ = build_r3_input(_base(), field_strength=0.01)
    for token in (
        "QPXFVMixtureAveragedDiffusion",
        "QPXFVHeavyMassElectromigrationCorrection",
        "QPXElectronTransportLookupMaterial",
        "property_name = n_e_physical",
        "expression = '${n_e_value}*ne_hat'",
        "electron_number_density = n_e_physical",
        "pressure = p",
        "gas_temperature = T_g",
        "variable = n_e",
    ):
        assert token in text
    for postprocessor in ("n_e_avg", "n_e_min", "n_e_max", "n_e_inventory"):
        assert mp.get_parameter(text, f"Postprocessors/{postprocessor}", "functor") == "n_e_physical"
    for forbidden in ("potential_plasma", "r30_phi_diffusion", "r30_phi_charge_source"):
        assert forbidden not in text


def test_issue91_governed_acceptance_queue_is_bounded_and_ordered() -> None:
    assert issue91_run.CASES == (
        ("R3_E0", "r3_e0", 0.0),
        ("R3_ECONST", "r3_econst", 0.01),
    )


def test_issue91_acceptance_stages_canonical_normalized_recipe(tmp_path) -> None:
    target = tmp_path / "R3_E0"
    staged = issue91_run._stage("R3_E0", "r3_e0", 0.0, target)
    text = (target / "input.i").read_text()

    assert staged["construction"]["audit"]["status"] == "PASS"
    assert staged["construction"]["electron_solver_unknown"] == "n_e == n_hat"
    assert mp.get_parameter(text, "Variables/n_e", "initial_condition") == "1.0"
    assert (
        mp.get_parameter(
            text,
            "FunctorMaterials/heavy_transport",
            "electron_number_density",
        )
        == "n_e_physical"
    )


def test_issue91_acceptance_physical_csv_excludes_initial_observation(tmp_path) -> None:
    case = tmp_path / "case"
    case.mkdir()
    raw = case / "input_out.csv"
    with raw.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("time", "n_e_avg"))
        writer.writeheader()
        writer.writerow({"time": "0", "n_e_avg": "1e16"})
        writer.writerow({"time": "1e-8", "n_e_avg": "1e16"})

    result = issue91_run._write_physical_csv(case)
    assert result["pass"] is True
    assert result["source_rows"] == 2
    assert result["physical_rows"] == 1

    with (case / "input_out.physical.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["time"] for row in rows] == ["1e-8"]
