from __future__ import annotations

import shutil

from experiments.Issue306_heavy_charge_motion import wall02_control


def test_issue306_wall02_contract(tmp_path, monkeypatch):
    generated = tmp_path / "generated_wall02"
    monkeypatch.setattr(wall02_control, "GENERATED", generated)
    try:
        summary = wall02_control.static_contract()
        assert summary["status"] == "PASS"
        assert summary["sequence"] == 2
        assert summary["chi_h"] == 40.0
        assert summary["heavy_cycles"] == 2
        assert summary["total_time_tau"] == 80.0

        for chi in (1, 10, 20):
            bulk = (generated / f"bulk_chi{chi}" / "input.i").read_text()
            wall = (generated / f"wall_chi{chi}" / "input.i").read_text()
            assert "PhysicsIonWallFluxMaterial" not in bulk
            assert wall.count("type = PhysicsIonWallFluxMaterial") == 3
            assert wall.count("ion_surface_mass_flux_left_") >= 6
            assert wall.count("ion_migration_mass_flux_left_") >= 6
            assert wall.count("boundaries_to_avoid = 'left right'") == 9
            assert "charge_number = -1" in wall
            assert "type = INSFVOutletPressureBC" in wall

            assert (
                generated / f"bulk_chi{chi}" / "fast_sub.i"
            ).read_text() == (
                generated / f"wall_chi{chi}" / "fast_sub.i"
            ).read_text()
    finally:
        shutil.rmtree(generated, ignore_errors=True)
