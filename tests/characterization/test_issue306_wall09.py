from __future__ import annotations

import shutil
from pathlib import Path

from experiments.Issue306_heavy_charge_motion import wall09_control


def test_issue306_wall09_standard_moose_sheath_contract(tmp_path, monkeypatch):
    generated = tmp_path / "generated_wall09"
    monkeypatch.setattr(wall09_control, "GENERATED", generated)
    try:
        summary = wall09_control.static_contract()
        assert summary["status"] == "PASS"
        assert summary["sequence"] == 9
        assert summary["chi_e"] == 100.0
        assert summary["ratios"] == [2, 4, 8]
        assert summary["chi_h"] == [200.0, 400.0, 800.0]
        assert summary["heavy_cycles"] == [300, 150, 75]
        assert summary["total_fast_steps"] == 600
        assert summary["final_tau"] == 60000.0

        for ratio, cycles in ((2, 300), (4, 150), (8, 75)):
            case = generated / f"bohm_sheath_ratio{ratio}"
            parent = (case / "input.i").read_text()
            fast = (case / "fast_sub.i").read_text()
            meta = (case / "case.json").read_text()

            assert f'"heavy_to_electron_dt_ratio": {ratio}' in meta
            assert f'"chi_h": {100.0 * ratio}' in meta
            assert f'"heavy_cycles": {cycles}' in meta
            assert '"fast_steps_total": 600' in meta

            assert f"num_steps = {cycles}" in parent
            assert parent.count("type = PhysicsIonWallFluxMaterial") == 3
            assert parent.count("sticking = 0.0") == 2
            assert parent.count("sticking = 1.0") == 1
            assert "bohm_surface_mass_flux_O2p" in parent
            assert "bohm_surface_mass_flux_Op" in parent
            assert "electron_temperature_wall_eV" in parent

            assert "[electron_sheath_factor]" in fast
            assert "ADParsedFunctorMaterial" in fast
            assert "exp(-(0.5*(phi+abs(phi)))/((2.0/3.0)*mean_ev))" in fast
            assert "0.5*exp(loge)" in fast
            assert "0.83333333333333333*eps_hat" in fast
            assert "[right_thermal_surface_loss]" in fast
            assert "[right_energy_surface_loss]" in fast
            assert "type = FVFunctorNeumannBC" in fast
            assert "PhysicsFVElectronGroundedSheath" not in fast
            assert "PhysicsFVElectronEnergyWallFluxBC" not in fast

        helper = (
            Path(__file__).resolve().parents[2]
            / "physics_app/include/fvbcs/PhysicsGroundedElectronSheathFlux.h"
        )
        assert not helper.exists()
    finally:
        shutil.rmtree(generated, ignore_errors=True)
