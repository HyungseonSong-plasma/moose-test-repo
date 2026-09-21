from __future__ import annotations

import shutil

from experiments.Issue253_g1_gummel_dt_release import analyze, prepare


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
