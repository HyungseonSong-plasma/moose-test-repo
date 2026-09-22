from __future__ import annotations

import shutil

from experiments.Issue306_heavy_charge_motion import wall03_control


def test_issue306_wall03_boundary_and_flux_contract(tmp_path, monkeypatch):
    generated = tmp_path / "generated_wall03"
    monkeypatch.setattr(wall03_control, "GENERATED", generated)
    try:
        summary = wall03_control.static_contract()
        assert summary["status"] == "PASS"
        assert summary["sequence"] == 3
        assert summary["chi_h"] == 40.0
        assert summary["heavy_cycles"] == 2
        assert summary["total_time_tau"] == 80.0

        for chi in (1, 10, 20):
            thermal_dir = generated / f"thermal_chi{chi}"
            comsol_dir = generated / f"comsol_chi{chi}"

            thermal = (thermal_dir / "input.i").read_text()
            comsol = (comsol_dir / "input.i").read_text()
            fast = (comsol_dir / "fast_sub.i").read_text()

            assert "type = WCNSFVMassFluxBC\n    variable = p\n    boundary = left" in comsol
            assert "type = INSFVOutletPressureBC\n    variable = p\n    boundary = right" in comsol
            assert "direction = '1 0 0'" in comsol

            assert "[right_thermal_surface_loss]" in fast
            assert "[right_energy_surface_loss]" in fast
            assert "0.5*exp(loge)" in fast
            assert "boundary = 'left right'" not in fast

            assert thermal.count("sticking = 1.0") == 3
            assert comsol.count("sticking = 0.0") == 2
            assert comsol.count("sticking = 1.0") == 1
            assert "bohm_surface_mass_flux_O2p" in comsol
            assert "bohm_surface_mass_flux_Op" in comsol
            assert "charge_number = -1" in comsol
            assert comsol.count("boundaries_to_avoid = 'left right'") == 9
    finally:
        shutil.rmtree(generated, ignore_errors=True)
