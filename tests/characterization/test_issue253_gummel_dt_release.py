from __future__ import annotations

import shutil
import subprocess
import sys

from experiments.Issue253_g1_gummel_dt_release import analyze, chi2_control, prepare


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
