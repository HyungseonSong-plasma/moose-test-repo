from __future__ import annotations

import shutil

from experiments.Issue306_heavy_charge_motion import wall05_control


def test_issue306_wall05_ultralong_relaxation_contract(tmp_path, monkeypatch):
    generated = tmp_path / "generated_wall05"
    monkeypatch.setattr(wall05_control, "GENERATED", generated)
    try:
        summary = wall05_control.static_contract()
        assert summary["status"] == "PASS"
        assert summary["sequence"] == 5
        assert summary["chi_e"] == 20.0
        assert summary["chi_h"] == 40.0
        assert summary["heavy_cycles"] == [100, 200, 300]
        assert summary["final_tau"] == [4000.0, 8000.0, 12000.0]

        for cycles in (100, 200, 300):
            case = generated / f"comsol_cycles{cycles}"
            meta = (case / "case.json").read_text()
            parent = (case / "input.i").read_text()
            fast = (case / "fast_sub.i").read_text()

            assert f'"heavy_cycles": {cycles}' in meta
            assert f'"fast_steps_total": {2 * cycles}' in meta
            assert f"num_steps = {cycles}" in parent
            assert "boundary = left" in parent
            assert "boundary = right" in parent
            assert "bohm_surface_mass_flux_O2p" in parent
            assert "bohm_surface_mass_flux_Op" in parent
            assert parent.count("boundaries_to_avoid = 'left right'") == 9
            assert "0.5*exp(loge)" in fast
            assert "[right_thermal_surface_loss]" in fast
            assert "[right_energy_surface_loss]" in fast
    finally:
        shutil.rmtree(generated, ignore_errors=True)
