from __future__ import annotations

import math
import shutil
import subprocess
import sys

from experiments.Issue253_g1_gummel_dt_release import heavy13_control


def test_issue253_g3_heavy13_equal_time_multirate_ab_contract() -> None:
    try:
        summary = heavy13_control.static_contract()
        assert summary["status"] == "PASS"
        assert summary["sequence"] == 13
        assert summary["total_time_tau_epsilon_initial"] == 80.0
        assert summary["heavy_dt_tau_epsilon_initial"] == 40.0
        assert summary["heavy_steps"] == 2

        cases = {str(item["name"]): item for item in summary["cases"]}
        assert set(cases) == {
            "frozen_chi1",
            "frozen_chi10",
            "frozen_chi20",
            "heavy_chi1",
            "heavy_chi10",
            "heavy_chi20",
        }

        expected = {1: 40, 10: 4, 20: 2}
        for chi, subcycles in expected.items():
            frozen = cases[f"frozen_chi{chi}"]
            released = cases[f"heavy_chi{chi}"]
            assert frozen["heavy_enabled"] is False
            assert released["heavy_enabled"] is True
            assert frozen["heavy_factor"] == 0.0
            assert released["heavy_factor"] == 1.0
            assert frozen["fast_subcycles_per_heavy_step"] == subcycles
            assert released["fast_subcycles_per_heavy_step"] == subcycles
            assert frozen["heavy_steps"] == released["heavy_steps"] == 2
            assert math.isclose(
                frozen["dt_heavy_s"] / frozen["dt_fast_s"],
                float(subcycles),
                rel_tol=1.0e-14,
            )
            assert math.isclose(
                frozen["end_time_s"], released["end_time_s"], rel_tol=0.0, abs_tol=0.0
            )
    finally:
        shutil.rmtree(heavy13_control.GENERATED, ignore_errors=True)


def test_issue253_g3_heavy13_changes_only_bulk_heavy_ownership() -> None:
    try:
        heavy13_control.static_contract()
        frozen = (
            heavy13_control.GENERATED / "frozen_chi10" / "input.i"
        ).read_text(encoding="utf-8")
        released = (
            heavy13_control.GENERATED / "heavy_chi10" / "input.i"
        ).read_text(encoding="utf-8")
        fast_frozen = (
            heavy13_control.GENERATED / "frozen_chi10" / "fast_sub.i"
        ).read_text(encoding="utf-8")
        fast_released = (
            heavy13_control.GENERATED / "heavy_chi10" / "fast_sub.i"
        ).read_text(encoding="utf-8")

        assert frozen.count("PhysicsFVConservativeMassFractionTimeDerivative") == 6
        assert released.count("PhysicsFVConservativeMassFractionTimeDerivative") == 6
        assert frozen.count("PhysicsFVMixtureAveragedDiffusion") == 6
        assert released.count("PhysicsFVMixtureAveragedDiffusion") == 6
        assert frozen.count("type = PhysicsFVElectrostaticDrift") == 3
        assert released.count("type = PhysicsFVElectrostaticDrift") == 3
        assert frozen.count("PhysicsFVHeavyMassElectromigrationCorrection") == 6
        assert released.count("PhysicsFVHeavyMassElectromigrationCorrection") == 6

        assert "prop_names = 'rho_const p_gas T_g heavy_factor'" in frozen
        assert "prop_names = 'rho_const p_gas T_g heavy_factor'" in released
        assert frozen != released
        assert fast_frozen == fast_released
        assert "PhysicsFVElectronEnergyJouleHeating" in fast_frozen
        assert "PhysicsElectronImpactRateMaterial" in fast_frozen
        assert "poisson_charge_C_m2" in fast_frozen
        assert "poisson_gauss_charge_C_m2" in fast_frozen
    finally:
        shutil.rmtree(heavy13_control.GENERATED, ignore_errors=True)


def test_issue253_g3_heavy13_runs_standalone_p0() -> None:
    try:
        completed = subprocess.run(
            [
                sys.executable,
                str(heavy13_control.ROOT / "heavy13_control.py"),
                "--phase",
                "p0",
            ],
            cwd=heavy13_control.REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert "ISSUE253_G3_HEAVY13_P0: PASS" in completed.stdout
    finally:
        shutil.rmtree(heavy13_control.GENERATED, ignore_errors=True)


def test_issue253_g3_sequence13_routes_to_central_matrix() -> None:
    workflow = (
        heavy13_control.REPO / ".github" / "workflows" / "experiment.yml"
    ).read_text(encoding="utf-8")
    assert "inputs.sequence == '12' || inputs.sequence == '13'" in workflow
    assert "governed-matrix.yml@464e0fa0e60e904dba7b2dfc1c960f4337713309" in workflow
