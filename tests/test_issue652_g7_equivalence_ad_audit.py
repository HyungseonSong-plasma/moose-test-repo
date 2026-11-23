"""G7 negative controls: old/new cannot acquire false semantic/AD passes."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "ci/guards/issue652_g7_equivalence_ad_audit.py"
SPEC = importlib.util.spec_from_file_location("issue652_g7_equivalence_ad_audit", MODULE)
assert SPEC and SPEC.loader
g7 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(g7)


def old(case):
    vals = {
        "time": 1e-4, "ne_min": 2.0e15, "ne_max": 8.4e16,
        "P_abs_maxwell_t6": 405.0,
        "rf_d8_poisson_charge_C": 1.234e-8,
    }
    return {
        "schema": "issue673.p3p4.public_d_original100_100us.v1",
        "source_HEAD": g7.OLD_SOURCE, "rf_enabled": True,
        "target_physical_steps": 460, "target_final_time_s": 1e-4,
        "RF_FULL_S6_CASES_PASS": True, "P3_P4_science": "SCIENCE_HOLD",
        "cases": {case: {
            "full_100us_rc": 0, "P3_timegrid_pass": True,
            "P4_diagnostic_only": True,
            "P4_series_invariant_pass": True,
            "full_S6_original_11_layers_unchanged": True,
            "seven_transfers_numeric_observed": True,
            "P3_temporal_summary": {"rows": 461, "physical_steps": 460},
            "csv_observed": [{"values": vals}],
            "d8_coupled_postprocessors": {"rf_d8_poisson_charge_C": 1.234e-8},
        }},
    }


def new(case):
    return {
        "schema": "issue652.g6b.native_100us_case.v1",
        "source_sha": g7.NEW_SOURCE, "case_id": case,
        "original_publicd_lookup_sha256": g7.LOOKUP_SHA,
        "P3_100us": "PASS_NATIVE_FINITE_461_FRAMES", "P4": "NOT_RUN",
        "science": "SCIENCE_HOLD",
        "original_s6_input_unchanged": True,
        "raw_protected_rates_in_artifact": False,
        "original_time_grid": {"end_time_seconds": 1e-4},
        "time_series": {
            "time_points": 461, "intervals": 460,
            "t_end_seconds": 1e-4,
            "extrema": {
                "ne_min": {"last": 2.5e15},
                "ne_max": {"last": 1.05e17},
                "charge_integral": {"last": 1.2e-8},
            },
        },
    }


def test_g7_old_new_scalar_readback_is_descriptive_only():
    for case in g7.CASES:
        a = g7.old_observables(old(case), case)
        b = g7.new_observables(new(case), case)
        assert g7.relative_delta(a["ne_max_m_minus3"], b["ne_max_m_minus3"])["relative_to_old"] == pytest.approx(.25)
        assert a["rf_coupled"] is True
        assert b["p4_status"] == "NOT_RUN_IN_G6B"


@pytest.mark.parametrize("field,value", [
    ("rf_enabled", False),
    ("source_HEAD", "a" * 40),
    ("RF_FULL_S6_CASES_PASS", False),
])
def test_g7_rejects_old_forged_readback(field, value):
    data = old("417")
    data[field] = value
    with pytest.raises(g7.AuditHold):
        g7.old_observables(data, "417")


def test_g7_rejects_missing_exact_old_parent_final():
    data = old("941")
    data["cases"]["941"]["csv_observed"] = []
    with pytest.raises(g7.AuditHold, match="NOT_UNIQUE"):
        g7.old_observables(data, "941")


@pytest.mark.parametrize("key,value", [
    ("P3_100us", "HOLD"),
    ("source_sha", "a" * 40),
    ("case_id", "941"),
    ("raw_protected_rates_in_artifact", True),
])
def test_g7_rejects_new_forged_or_wrong_case(key, value):
    data = new("417")
    data[key] = value
    with pytest.raises(g7.AuditHold):
        g7.new_observables(data, "417")


def test_g7_source_charge_sign_and_numeric_derivative():
    source = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    result = g7.verify_charge_source(source)
    assert result["algebraic_status"] == "PASS_INDEPENDENT_FORMULA_FD"
    assert result["petsc_assembled_jacobian"] == "NOT_RUN"
    assert {v["state"]: v["sign"] for v in result["algebraic_log_density_derivatives"]} == {
        "log_O2p": 1, "log_Op": 1, "log_e": -1, "log_Om": -1,
    }
    assert max(v["relative_error"] for v in result["algebraic_log_density_derivatives"]) < 3e-9


def test_g7_mutated_charge_sign_and_scale_fail_closed():
    source = (ROOT / "physics_app/src/physics/plasma/Chemistry.C").read_text()
    for altered in (
        source.replace('"ni+nop-ne-nm"', '"ni+nop+ne-nm"'),
        source.replace('"1.8095128179727827e-08*nq"', '"9e-8*nq"'),
        source.replace('"ADParsedFunctorMaterial"', '"ParsedFunctorMaterial"'),
    ):
        with pytest.raises(g7.AuditHold, match="SOURCE_DRIFT"):
            g7.verify_charge_source(altered)


def test_g7_incomplete_comparison_fails_without_output(tmp_path):
    for case in g7.CASES:
        for prefix, data, filename in (
            ("old", old(case), "rf_full_s6_receipt.json"),
            ("new", new(case), "g6b-full100-" + case + ".json"),
        ):
            folder = tmp_path / (prefix + case)
            folder.mkdir()
            (folder / filename).write_text(json.dumps(data))
    (tmp_path / "new941" / "g6b-full100-941.json").unlink()
    with pytest.raises(g7.AuditHold):
        g7.analyze(
            old417=tmp_path / "old417", old941=tmp_path / "old941",
            new417=tmp_path / "new417", new941=tmp_path / "new941",
            cpp=ROOT / "physics_app/src/physics/plasma/Chemistry.C",
            output=tmp_path / "result.json",
        )
    assert not (tmp_path / "result.json").exists()


def test_g7_complete_report_is_science_hold_not_parity(tmp_path):
    for case in g7.CASES:
        for prefix, data, filename in (
            ("old", old(case), "rf_full_s6_receipt.json"),
            ("new", new(case), "g6b-full100-" + case + ".json"),
        ):
            folder = tmp_path / (prefix + case)
            folder.mkdir()
            (folder / filename).write_text(json.dumps(data))
    result = g7.analyze(
        old417=tmp_path / "old417", old941=tmp_path / "old941",
        new417=tmp_path / "new417", new941=tmp_path / "new941",
        cpp=ROOT / "physics_app/src/physics/plasma/Chemistry.C",
        output=tmp_path / "result.json",
    )
    assert result["science"] == "SCIENCE_HOLD"
    assert result["source_input_identity"].startswith("HOLD")
    assert result["jacobian"]["petsc_assembled_jacobian"] == "NOT_RUN"
    assert result["cases"]["417"]["same_input_status"].startswith("HOLD")
    assert result["cases"]["941"]["physical_equivalence"] == "UNPROVEN"
