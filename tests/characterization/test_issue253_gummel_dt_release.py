from __future__ import annotations

import math
import shutil
import subprocess
import sys

from experiments.Issue253_g1_gummel_dt_release import analyze, chi2_control, energy09_control, energy10_control, extended_control, extreme08_control, final_control, ion_advance_control, parallel_control, prepare, relaxed_control


def test_issue253_g1_case_matrix_preserves_single_model() -> None:
    try:
        summary = prepare.static_contract()
        assert summary["status"] == "PASS"
        cases = {str(item["name"]): item for item in summary["cases"]}
        assert cases["ref_chi0p1"]["chi"] == 0.1
        assert cases["onepass_chi5"]["chi"] == 5.0
        assert cases["gummel_chi5"]["chi"] == 5.0
        assert cases["onepass_chi5"]["dt_s"] == cases["gummel_chi5"]["dt_s"]
        assert cases["onepass_chi5"]["fp_max"] == 1
        assert cases["gummel_chi5"]["fp_min"] == 2
        assert cases["gummel_chi5"]["fp_max"] == 30
    finally:
        shutil.rmtree(prepare.GENERATED, ignore_errors=True)


def _metrics(phi: float, ne: float, field: float) -> dict[str, float]:
    return {"phi_einf": phi, "ne_einf": ne, "e_einf": field}


def test_issue253_g1_gummel_negative_control_requires_iteration() -> None:
    classification, valid, _ = analyze.classify_result(
        _metrics(2.0, 1.0, 1.0),
        _metrics(0.01, 0.01, 0.01),
        fixed_point_iterations=1.0,
    )
    assert classification == "GUMMEL_NOT_EXERCISED"
    assert valid is False


def test_issue253_g1_release_requires_joint_phi_density_field_recovery() -> None:
    one = _metrics(2.0, 1.0, 1.0)

    classification, valid, _ = analyze.classify_result(
        one,
        _metrics(0.05, 0.05, 0.05),
        fixed_point_iterations=4.0,
    )
    assert (classification, valid) == ("DT_RELEASE_SUPPORTED", True)

    classification, valid, ratios = analyze.classify_result(
        one,
        _metrics(0.5, 0.2, 0.2),
        fixed_point_iterations=4.0,
    )
    assert (classification, valid) == ("PARTIAL_RELEASE", True)
    assert all(ratios[key] <= 0.75 for key in analyze.PRIMARY_ERROR_METRICS)

    classification, valid, ratios = analyze.classify_result(
        one,
        _metrics(0.5, 1.2, 1.2),
        fixed_point_iterations=4.0,
    )
    assert (classification, valid) == ("MIXED_RESPONSE", True)
    assert ratios["phi_einf"] <= 0.75
    assert ratios["ne_einf"] > 0.75
    assert ratios["e_einf"] > 0.75


def test_issue253_g1_chi2_control_is_plain_gummel() -> None:
    try:
        summary = chi2_control.static_contract()
        case = summary["case"]
        assert summary["status"] == "PASS"
        assert case["chi"] == 2.0
        assert case["steps"] == 10
        assert case["fp_min"] == 2
        assert case["fp_max"] == 30
    finally:
        shutil.rmtree(chi2_control.GENERATED, ignore_errors=True)


def test_issue253_g1_chi2_runtime_classifies_scientific_divergence_as_valid() -> None:
    classification, valid = chi2_control.classify_runtime(
        returncode=1,
        log_text="Fixed point convergence reason: DIVERGED_MAX_ITS",
        final_time=None,
        expected_end_time=1.0,
        fixed_point_iterations=None,
    )
    assert (classification, valid) == ("GUMMEL_DIVERGED", True)


def test_issue253_g1_chi2_runtime_requires_complete_horizon_for_convergence() -> None:
    classification, valid = chi2_control.classify_runtime(
        returncode=0,
        log_text="",
        final_time=1.0,
        expected_end_time=1.0,
        fixed_point_iterations=4.0,
    )
    assert (classification, valid) == ("GUMMEL_CONVERGED", True)

    classification, valid = chi2_control.classify_runtime(
        returncode=0,
        log_text="",
        final_time=0.5,
        expected_end_time=1.0,
        fixed_point_iterations=4.0,
    )
    assert (classification, valid) == ("INCOMPLETE_PHYSICAL_HORIZON", False)


def test_issue253_g1_chi2_control_runs_standalone_p0() -> None:
    try:
        completed = subprocess.run(
            [sys.executable, str(chi2_control.ROOT / "chi2_control.py"), "--phase", "p0"],
            cwd=chi2_control.REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert "ISSUE253_G1_CHI2_P0: PASS" in completed.stdout
    finally:
        shutil.rmtree(chi2_control.GENERATED, ignore_errors=True)


def test_issue253_g1_relaxed_control_uses_physics_scaled_poisson_relaxation() -> None:
    try:
        summary = relaxed_control.static_contract()
        assert summary["status"] == "PASS"
        assert math.isclose(summary["omega"], 1.0 / 6.0, rel_tol=0.0, abs_tol=1e-16)
        cases = {str(item["name"]): item for item in summary["cases"]}
        assert cases["relaxed_gummel_chi5"]["chi"] == 5.0
        assert cases["relaxed_gummel_chi5"]["fp_min"] == 2
        assert cases["relaxed_gummel_chi5"]["fp_max"] == 30
    finally:
        shutil.rmtree(relaxed_control.GENERATED, ignore_errors=True)


def test_issue253_g1_relaxed_control_runs_standalone_p0() -> None:
    try:
        completed = subprocess.run(
            [sys.executable, str(relaxed_control.ROOT / "relaxed_control.py"), "--phase", "p0"],
            cwd=relaxed_control.REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert "ISSUE253_G1_RELAXED_P0: PASS" in completed.stdout
    finally:
        shutil.rmtree(relaxed_control.GENERATED, ignore_errors=True)


def test_issue253_g1_relaxed_picard_parser_handles_ansi() -> None:
    text = "\x1b[35m 1 Picard |R| = 1.25e-03\x1b[0m"
    assert relaxed_control._picard_residuals(text) == [1.25e-03]


def test_issue253_g1_final_matrix_fixed_total_time_and_cost_budget() -> None:
    try:
        summary = final_control.static_contract()
        assert summary["status"] == "PASS"
        assert summary["total_time_tau_epsilon"] == 200.0
        cases = {str(item["name"]): item for item in summary["cases"]}
        assert cases["ref_chi0p1"]["steps"] == 2000
        assert cases["relaxed_chi10"]["steps"] == 20
        assert cases["relaxed_chi100"]["steps"] == 2
        assert math.isclose(
            cases["relaxed_chi10"]["relaxation_factor"], 1.0 / 11.0,
            rel_tol=0.0, abs_tol=1e-16
        )
        assert math.isclose(
            cases["relaxed_chi100"]["relaxation_factor"], 1.0 / 101.0,
            rel_tol=0.0, abs_tol=1e-16
        )
        assert cases["relaxed_chi10"]["fp_max"] == 70
        assert cases["relaxed_chi100"]["fp_max"] == 700
        assert cases["relaxed_chi10"]["steps"] * cases["relaxed_chi10"]["fp_max"] == 1400
        assert cases["relaxed_chi100"]["steps"] * cases["relaxed_chi100"]["fp_max"] == 1400
    finally:
        shutil.rmtree(final_control.GENERATED, ignore_errors=True)


def test_issue253_g1_final_control_runs_standalone_p0() -> None:
    try:
        completed = subprocess.run(
            [sys.executable, str(final_control.ROOT / "final_control.py"), "--phase", "p0"],
            cwd=final_control.REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert "ISSUE253_G1_FINAL_P0: PASS" in completed.stdout
    finally:
        shutil.rmtree(final_control.GENERATED, ignore_errors=True)


def test_issue253_g1_extreme_matrix_fixed_total_time_and_budget() -> None:
    try:
        summary = extended_control.static_contract()
        assert summary["status"] == "PASS"
        assert summary["total_time_tau_epsilon"] == 20000.0
        cases = {str(item["name"]): item for item in summary["cases"]}
        assert cases["ref_chi0p1"]["steps"] == 200000
        assert cases["relaxed_chi1000"]["steps"] == 20
        assert cases["relaxed_chi10000"]["steps"] == 2
        assert cases["relaxed_chi1000"]["fp_max"] == 7000
        assert cases["relaxed_chi10000"]["fp_max"] == 70000
        assert math.isclose(
            cases["relaxed_chi1000"]["relaxation_factor"], 1.0 / 1001.0,
            rel_tol=0.0, abs_tol=1e-16
        )
        assert math.isclose(
            cases["relaxed_chi10000"]["relaxation_factor"], 1.0 / 10001.0,
            rel_tol=0.0, abs_tol=1e-16
        )
        assert cases["relaxed_chi1000"]["steps"] * cases["relaxed_chi1000"]["fp_max"] == 140000
        assert cases["relaxed_chi10000"]["steps"] * cases["relaxed_chi10000"]["fp_max"] == 140000
    finally:
        shutil.rmtree(extended_control.GENERATED, ignore_errors=True)


def test_issue253_g1_extreme_control_runs_standalone_p0() -> None:
    try:
        completed = subprocess.run(
            [sys.executable, str(extended_control.ROOT / "extended_control.py"), "--phase", "p0"],
            cwd=extended_control.REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert "ISSUE253_G1_EXTREME_P0: PASS" in completed.stdout
    finally:
        shutil.rmtree(extended_control.GENERATED, ignore_errors=True)


def test_issue253_g1_ion_advance_contract_has_two_solved_ion_steps() -> None:
    try:
        summary = ion_advance_control.static_contract()
        assert summary["status"] == "PASS"
        assert summary["ion_species"] == "O2+"
        assert summary["ion_steps"] == 2
        assert math.isclose(summary["ion_dt_s"], 1.0e-4, rel_tol=0.0, abs_tol=0.0)
        assert summary["expected_free_drift_shift_m"] > 0.0
    finally:
        shutil.rmtree(ion_advance_control.GENERATED, ignore_errors=True)


def test_issue253_g1_ion_advance_control_runs_standalone_p0() -> None:
    try:
        completed = subprocess.run(
            [sys.executable, str(ion_advance_control.ROOT / "ion_advance_control.py"), "--phase", "p0"],
            cwd=ion_advance_control.REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert "ISSUE253_G1_ION_ADVANCE_P0: PASS" in completed.stdout
    finally:
        shutil.rmtree(ion_advance_control.GENERATED, ignore_errors=True)


def test_issue253_g1_parallel_matrix_fixed_T20_has_200_20_2_steps() -> None:
    try:
        summary = parallel_control.static_contract()
        assert summary["status"] == "PASS"
        assert summary["total_time_tau_epsilon"] == 20.0
        cases = {str(item["name"]): item for item in summary["cases"]}
        assert cases["ref_chi0p1"]["steps"] == 200
        assert cases["relaxed_chi1"]["steps"] == 20
        assert cases["relaxed_chi10"]["steps"] == 2
        assert math.isclose(cases["relaxed_chi1"]["relaxation_factor"], 0.5)
        assert math.isclose(cases["relaxed_chi10"]["relaxation_factor"], 1.0 / 11.0)
    finally:
        shutil.rmtree(parallel_control.GENERATED, ignore_errors=True)


def test_issue253_g1_parallel_control_runs_standalone_p0() -> None:
    try:
        completed = subprocess.run(
            [sys.executable, str(parallel_control.ROOT / "parallel_control.py"), "--phase", "p0"],
            cwd=parallel_control.REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
        assert "ISSUE253_G1_PARALLEL_P0: PASS" in completed.stdout
    finally:
        shutil.rmtree(parallel_control.GENERATED, ignore_errors=True)


def test_issue253_g1_parallel_matrix_is_central_workflow_owned() -> None:
    workflow = (parallel_control.REPO / ".github" / "workflows" / "experiment.yml").read_text(encoding="utf-8")
    assert "governed-matrix.yml@464e0fa0e60e904dba7b2dfc1c960f4337713309" in workflow
    assert "parallel-prepare:" not in workflow
    assert "parallel-run:" not in workflow
    assert "parallel-aggregate:" not in workflow


def test_issue253_g1_extreme08_equal_time_matrix() -> None:
    try:
        summary = extreme08_control.static_contract()
        assert summary["status"] == "PASS"
        assert summary["total_time_tau_epsilon"] == 1000.0
        cases = {str(item["name"]): item for item in summary["cases"]}
        expected = {
            "relaxed_chi10": (10.0, 100),
            "relaxed_chi100": (100.0, 10),
            "relaxed_chi1000": (1000.0, 1),
        }
        for name, (chi, steps) in expected.items():
            item = cases[name]
            assert item["chi"] == chi
            assert item["steps"] == steps
            assert math.isclose(item["dt_s"] * steps, item["end_time_s"], rel_tol=1e-14)
            assert math.isclose(item["relaxation_factor"], 1.0 / (1.0 + chi), rel_tol=1e-14)
            input_text = (
                extreme08_control.GENERATED / name / "input.i"
            ).read_text(encoding="utf-8")
            assert "[final_exodus]" in input_text
            assert "type = Exodus" in input_text
            assert "[final_csv]" in input_text
            assert input_text.count("execute_on = 'FINAL'") >= 3
    finally:
        shutil.rmtree(extreme08_control.GENERATED, ignore_errors=True)


def test_issue253_g1_experiment_workflow_routes_sequence08_to_central_matrix() -> None:
    workflow = (extreme08_control.REPO / ".github" / "workflows" / "experiment.yml").read_text(encoding="utf-8")
    assert "inputs.sequence == '07' || inputs.sequence == '08'" in workflow


def test_issue253_g2_energy09_wall_always_on_joule_elastic_matrix() -> None:
    try:
        summary = energy09_control.static_contract()
        assert summary["status"] == "PASS"
        assert summary["energy_wall_flux"] == "ALWAYS_ON"
        assert summary["wall_closure"] == "COMSOL_HALF_MAXWELLIAN_5_OVER_6"
        assert summary["wall_particle_flux"] == "Gamma=(1/2)*n_e*v_th"
        assert summary["wall_energy_flux"] == "q=(5/6)*n_epsilon*v_th"
        assert summary["wall_energy_per_lost_electron"] == "(5/3)*mean_en=(5/2)*T_e"
        assert summary["chi"] == 10.0
        assert summary["total_time_tau_epsilon_initial"] == 1000.0
        cases = {str(item["name"]): item for item in summary["cases"]}
        assert set(cases) == {"wall_j0_e0", "wall_j1_e0", "wall_j0_e1", "wall_j1_e1"}
        assert all(item["energy_wall_flux"] is True for item in cases.values())
        assert cases["wall_j0_e0"]["joule_heating"] is False
        assert cases["wall_j0_e0"]["elastic_collision"] is False
        assert cases["wall_j1_e0"]["joule_heating"] is True
        assert cases["wall_j1_e0"]["elastic_collision"] is False
        assert cases["wall_j0_e1"]["joule_heating"] is False
        assert cases["wall_j0_e1"]["elastic_collision"] is True
        assert cases["wall_j1_e1"]["joule_heating"] is True
        assert cases["wall_j1_e1"]["elastic_collision"] is True
    finally:
        shutil.rmtree(energy09_control.GENERATED, ignore_errors=True)


def test_issue253_g2_sequence09_routes_to_central_matrix() -> None:
    workflow = (energy09_control.REPO / ".github" / "workflows" / "experiment.yml").read_text(encoding="utf-8")
    assert "inputs.sequence == '07' || inputs.sequence == '08' || inputs.sequence == '09'" in workflow


def test_issue253_g2_energy09_accepts_measured_nonlinear_floor() -> None:
    try:
        energy09_control.static_contract()
        text = (
            energy09_control.GENERATED / "wall_j1_e1" / "input.i"
        ).read_text(encoding="utf-8")
        assert "nl_abs_tol = 2.0e-7" in text
    finally:
        shutil.rmtree(energy09_control.GENERATED, ignore_errors=True)


def test_issue253_g2_energy10_equal_time_joule_chi_sweep() -> None:
    try:
        summary = energy10_control.static_contract()
        assert summary["status"] == "PASS"
        assert summary["total_time_tau_epsilon_initial"] == 100.0
        assert summary["energy_equation"] == "ON"
        assert summary["joule_heating"] == "ON"
        assert summary["elastic_collision"] == "OFF"
        cases = {str(item["name"]): item for item in summary["cases"]}
        expected = {
            "joule_chi1": (1.0, 100, 0.5),
            "joule_chi10": (10.0, 10, 1.0 / 11.0),
            "joule_chi100": (100.0, 1, 1.0 / 101.0),
        }
        for name, (chi, steps, omega) in expected.items():
            item = cases[name]
            assert item["chi"] == chi
            assert item["steps"] == steps
            assert item["joule_heating"] is True
            assert item["elastic_collision"] is False
            assert math.isclose(item["relaxation_factor"], omega, rel_tol=1e-14)
            assert math.isclose(
                item["dt_s"] * item["steps"], item["end_time_s"], rel_tol=1e-14
            )
    finally:
        shutil.rmtree(energy10_control.GENERATED, ignore_errors=True)


def test_issue253_g2_sequence10_routes_to_central_matrix() -> None:
    workflow = (energy10_control.REPO / ".github" / "workflows" / "experiment.yml").read_text(encoding="utf-8")
    assert "inputs.sequence == '07' || inputs.sequence == '08' || inputs.sequence == '09' || inputs.sequence == '10'" in workflow
