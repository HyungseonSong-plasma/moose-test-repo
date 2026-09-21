from __future__ import annotations

import shutil

from experiments.Issue253_g1_gummel_dt_release import prepare


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


def test_issue253_g1_gummel_negative_control_requires_iteration() -> None:
    spec = dict(next(x for x in prepare.CASES if x["name"] == "gummel_chi5"))
    spec["fp_max"] = 1
    params = prepare.case_parameters(spec)
    assert params["chi"] == 5.0
    assert params["fp_max"] == 1
    assert params["fp_max"] <= 1
