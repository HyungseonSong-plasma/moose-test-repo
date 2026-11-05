"""Static provenance guard for the selected oxygen ICP research chemistry base.

This does not simulate Physics or validate reaction physics. It prevents a
numerical working reference from silently becoming production acceptance.
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = (
    Path(__file__).resolve().parents[2]
    / "experiments"
    / "Issue395_powered_chemistry_ladder"
    / "research_baselines"
)
EXPECTED_ACTIVE = [
    "EI-01", "EI-02", "DISS-G", "EI-16", "EI-17", "EI-941",
    "EI-2738", "EI-407", "EI-417", "EI-935", "H24", "H25",
    "H23", "EI-2069",
]
EXPECTED_EXCLUDED = {
    "EI-20", "EI-943", "EI-2259", "EI-2058", "H05",
    "EI-2072", "EI-2074",
}
SOURCE_SHA = "e2f2080649784a04f3300ea9dded1ae23b0a04b1"
PHYSICS_SHA = "8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
EEDF_SHA = "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"


def read_base() -> dict:
    data = json.loads((BASE / "current_reaction_base.json").read_text())
    assert data["schema_version"] == "oxygen_icp_research_reaction_base_v1"
    return data


def is_hash(s: str, digits: int = 64) -> bool:
    return len(s) == digits and all(c in "0123456789abcdef" for c in s)


def test_research_only_authority_and_explicit_science_hold() -> None:
    b = read_base()
    assert b["designation"] == "CURRENT_WORKING_REACTION_BASE"
    assert b["acceptance"] == "SCIENCE_HOLD"
    assert b["replay_policy"]["science_acceptance_must_remain"] == "HOLD"
    assert "production chemistry acceptance" in b["authority_boundary"]["not_promoted"]
    assert "scientific validation" in b["authority_boundary"]["not_promoted"]
    assert "canonical Oxygen25/Issue419 reaction registry" in b["authority_boundary"]["not_promoted"]
    assert b["chemistry"]["no_automated_production_promotion"] is True


def test_exact_14_active_inventory_and_single_replacement() -> None:
    b = read_base()
    chemistry = b["chemistry"]
    active = chemistry["active_channels"]
    assert active == EXPECTED_ACTIVE
    assert chemistry["active_channel_count"] == len(set(active)) == 14
    assert EXPECTED_EXCLUDED.issubset(set(chemistry["excluded_parent_channels"]))
    assert not EXPECTED_EXCLUDED.intersection(active)
    assert chemistry["EI2069_active"] is True
    assert chemistry["EI943_active"] is False
    assert chemistry["EI2738_rate_mode"] == (
        "MCS_24case_derived_lookup_with_analytical_tails_provisional"
    )
    assert chemistry["explicit_replacement"] == {
        "removed": "EI-20", "added": "EI-941", "parallel_use_prohibited": True
    }
    assert b["authority_boundary"]["only_chemistry_change_from_predecessor"] == (
        "EI-20 -> EI-941, exclusive replacement"
    )
    assert b["authority_boundary"][
        "subsequent_EI401_EI412_EI415_replacements_are_not_in_this_base"
    ] is True
    assert b["authority_boundary"]["EI2069_removal_experiment_is_not_in_this_base"] is True


def test_reproducibility_and_native_evidence() -> None:
    b = read_base()
    src = b["source"]
    assert src["immutable_verified_harness_sha"] == SOURCE_SHA
    assert src["physics_app_pinned_sha"] == PHYSICS_SHA
    assert src["fixed_initial_eedf_sha256"] == EEDF_SHA
    assert src["reference_branch"] == "base/oxygen-icp-14ch-h23-ei941-20261105"
    assert src["action_run"].endswith("/42043664537")
    conditions = b["operating_conditions"]
    assert conditions["power_W"] == [400, 1000]
    assert conditions["end_time_s"] == 0.0001
    assert conditions["expected_native_timestep_count"] == 460
    assert conditions["recorded_csv_time_count"] == 461
    assert conditions["neutral_inlet_sccm"] == 200
    assert conditions["neutral_wall_sticking"] == 1
    assert conditions["native_initialization"] == "fresh_not_restarted"
    assert conditions["transport_eedf_sha256"] == EEDF_SHA
    ids = {"400W": 13445953720, "1000W": 13446601738}
    for power, artifact_id in ids.items():
        v = b["verified_runs"][power]
        assert v["run_id"] == 42043664537
        assert v["artifact_id"] == artifact_id
        assert v["native_checkpoint_verified"] is True
        assert v["native_P0_P4_pass"] is True
        assert v["verified_endpoint_s"] == 0.0001
        assert v["native_steps"] == 460
        assert power in v["artifact_name"]
        for key in ("artifact_zip_sha256", "native_run_archive_sha256",
                    "native_inputs_archive_sha256"):
            assert is_hash(v[key])
        assert abs(v["last_rf_power_W"] - int(power[:-1])) < 5


def test_original_rates_are_provenance_only_not_public_data() -> None:
    b = read_base()
    rates = b["rate_provenance"]
    assert rates["EI-941"]["private"] is True
    assert rates["EI-2069"]["private"] is True
    assert rates["EI-2738"]["private"] is False
    assert rates["EI-2738"]["model_mapping_provisional"] is True
    for name in ("EI-941", "EI-2069", "EI-2738"):
        assert is_hash(rates[name]["sha256"])
    assert rates["EI-941"]["electron_loss_eV"] == 13.62
    assert rates["EI-2069"]["electron_loss_eV"] == 5.02
    files = {p.name for p in BASE.rglob("*") if p.is_file()}
    assert files == {"README.md", "current_reaction_base.json"}


def test_human_readable_contract_keeps_research_scope() -> None:
    text = (BASE / "README.md").read_text()
    for fragment in (
        "CURRENT_WORKING_REACTION_BASE",
        "SCIENCE_HOLD" if "SCIENCE_HOLD" in text else "HOLD",
        "Run #42043664537", SOURCE_SHA, "EI-2069",
        "EI-941", "EI-20", "EI-401", "EI-412", "EI-415",
        "Issue #419",
    ):
        assert fragment in text
