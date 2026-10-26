"""Independent P0 audit of the 200/600/1000 W ground-state O2 campaign."""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHEM = ROOT / "experiments/Issue395_powered_chemistry_ladder"
AUDITOR = CHEM / "analyze_ground_state_power_scan.py"
REPLAY = CHEM / "issue397_l1_power_scan_replay.sh"
WORKFLOW = ROOT / ".github/workflows/issue395-ground-state-three-power-once.yml"


def load_auditor():
    spec = importlib.util.spec_from_file_location("ground_state_three_power_audit", AUDITOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def case(tmp_path: Path, *, power_w: int, energy=-12.0, source=0.064,
         closure=0.0, scaled_w=None, drive=1.0, end_time=100e-6,
         rate=2.0, with_d1=True):
    result = tmp_path / f"case-{power_w}"
    (result / "run").mkdir(parents=True)
    with (result / "run/plasma.csv").open("w", newline="", encoding="utf-8") as stream:
        row = {
            "time": end_time,
            "diss_R_integral": rate,
            "diss_energy_source_integral": energy,
            "diss_O_mass_source_integral": source,
            "diss_heavy_mass_closure_integral": closure,
            "rf_drive_scale_t6": drive,
            "P_rf_scaled_W_t6": power_w if scaled_w is None else scaled_w,
            "P_abs_maxwell_t6": power_w * 0.95,
        }
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    if with_d1:
        (result / "d1_native").mkdir()
        (result / "d1_native/d1_native_summary.json").write_text(
            json.dumps({
                "status": "D1_NATIVE_DIAGNOSTIC_INTEGRITY_PASS",
                "wafer_faces": 27, "native_points": 461, "final_time_us": 100.0,
            }),
            encoding="utf-8",
        )
    return result


@pytest.mark.parametrize("power_w", [200, 600, 1000])
def test_positive_control_is_classified_at_each_target(tmp_path: Path, power_w: int):
    audit = load_auditor().audit
    result = audit(case(tmp_path, power_w=power_w), power_w, "sha", "success", "success")
    assert result["status"] == "PASS"
    assert all(v["status"] == "PASS" for v in result["checks"].values())


@pytest.mark.parametrize("fault", ["wrong_energy", "mass_source", "pid_cap", "short_run", "no_d1"])
def test_independent_negative_controls_never_pass(tmp_path: Path, fault: str):
    opts = {
        "wrong_energy": {"energy": -25.24},
        "mass_source": {"source": 0.032},
        "pid_cap": {"drive": 3.0},
        "short_run": {"end_time": 57e-9},
        "no_d1": {"with_d1": False},
    }
    result = load_auditor().audit(case(tmp_path, power_w=600, **opts[fault]), 600, "sha", "success", "success")
    assert result["status"] == "NOT_PASS"


def test_guarded_main_only_one_shot_and_replay_power_scope():
    source = WORKFLOW.read_text(encoding="utf-8")
    replay = REPLAY.read_text(encoding="utf-8")
    assert "branches: [main]" in source
    assert "paths: [.github/workflows/issue395-ground-state-three-power-once.yml]" in source
    assert "power_w: [200, 600, 1000]" in source
    assert "timeout-minutes: 360" in source
    assert "max-parallel: 3" in source
    assert "if: always()" in source
    assert 'case "$POWER_W" in 200|250|300|600|1000)' in replay
    assert "DISS_ENERGY_LOSS_EV = 6.0" in (
        CHEM / "build_o2_dissociation_overlay.py"
    ).read_text(encoding="utf-8")


def test_corrected_fem_wall_owners_registered_and_share_plasma_sided_functor():
    """P0 regression for P2 failure in the first 200/600/1000 W attempt.

    Reject an unregistered BC and any implementation that evaluates the
    adjacent-sheath functor through its thermal-only ElemQp fallback.
    Actual C++ registration/parameter compatibility remains a P2 obligation.
    """
    bc = ROOT / "physics_app/src/bcs/PhysicsFEMLogMolarElectronFieldLimitedFluxBC.C"
    content = bc.read_text(encoding="utf-8")
    for name in (
        "PhysicsFEMLogMolarElectronFieldLimitedFluxBC",
        "PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC",
    ):
        assert f'registerMooseObject("PhysicsApp", {name});' in content
        assert f"{name}::validParams()" in content
    assert "checkVariableBoundaryIntegrity() const override { return false; }" in content
    assert "getFunctor<ADReal>(\"wall_number_flux\")" in content
    assert "getFunctor<ADReal>(\"mean_energy\")" in content
    assert "hasFaceSide(*fi, true)" in content
    assert "hasFaceSide(*fi, false)" in content
    assert "plasma_side != _current_elem" in content
    assert "Moose::FaceArg face_arg" in content
    assert "PHYSICS_CONSTANTS::N_A" in content
    assert "(2.5 * Te)" in content
    assert "Moose::ElemQpArg" not in content

    generator = (CHEM / "enable_electron_adjacent_sheath_wall.py").read_text(encoding="utf-8")
    assert "type = PhysicsFEMLogMolarElectronFieldLimitedFluxBC" in generator
    assert "type = PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC" in generator
    assert "wall_number_flux = electron_wall_number_flux" in generator
