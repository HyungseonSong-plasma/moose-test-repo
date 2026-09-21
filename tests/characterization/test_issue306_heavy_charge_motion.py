from __future__ import annotations

from experiments.Issue306_heavy_charge_motion import control


def test_issue306_heavy_release_matrix_is_equal_time(tmp_path, monkeypatch):
    generated = tmp_path / "generated"
    monkeypatch.setattr(control, "GENERATED", generated)
    summary = control.static_contract()

    assert summary["status"] == "PASS"
    assert summary["chi_h"] == 40.0
    assert summary["heavy_cycles"] == 2
    assert summary["total_time_tau"] == 80.0

    by = {case["name"]: case for case in summary["matrix"]}
    assert by["frozen_chi1"]["fast_steps_per_heavy_cycle"] == 40
    assert by["frozen_chi10"]["fast_steps_per_heavy_cycle"] == 4
    assert by["frozen_chi20"]["fast_steps_per_heavy_cycle"] == 2

    for chi in (1, 10, 20):
        frozen = generated / f"frozen_chi{chi}"
        released = generated / f"released_chi{chi}"
        assert (frozen / "fast_sub.i").read_text() == (released / "fast_sub.i").read_text()


def test_issue306_released_parent_only_adds_current_heavy_owners(tmp_path, monkeypatch):
    generated = tmp_path / "generated"
    monkeypatch.setattr(control, "GENERATED", generated)
    control.build()

    released = (generated / "released_chi1" / "input.i").read_text()
    frozen = (generated / "frozen_chi1" / "input.i").read_text()

    assert "solve = false" in frozen
    assert "PhysicsFVConservativeMassFractionTimeDerivative" not in frozen

    assert released.count("type = PhysicsFVConservativeMassFractionTimeDerivative") == 6
    assert released.count("type = PhysicsFVMassFractionAdvection") == 6
    assert released.count("type = PhysicsFVMixtureAveragedDiffusion") == 6
    assert released.count("type = PhysicsFVElectrostaticDrift") == 3
    assert released.count("type = PhysicsFVHeavyMassElectromigrationCorrection") == 6

    assert "type = WCNSFVMassFluxBC" in released
    assert "type = WCNSFVMomentumFluxBC" in released
    assert released.count("type = WCNSFVScalarFluxBC") == 6
    assert "type = INSFVOutletPressureBC" in released
    assert "execute_on = TIMESTEP_END" in released
    assert "sub_cycling = true" in released
