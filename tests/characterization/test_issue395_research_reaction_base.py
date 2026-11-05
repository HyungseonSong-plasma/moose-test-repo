"""Guard current (research-only) Oxygen ICP 14-channel BASE and frozen predecessor.

This checks recorded run provenance and source/owner contracts; it does not
validate collision cross sections, chemical physics, or numerical solver runtime.
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
HISTORY = BASE / "history" / "oxygen-icp-h23-no943-mcs2738-ei2069-ei941-14ch-20261105.json"
SOURCE_SHA = "29d1acc6ef7969908b86719e4b95c73a1565136d"
OLD_SOURCE_SHA = "e2f2080649784a04f3300ea9dded1ae23b0a04b1"
PHYSICS_SHA = "8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
EEDF_SHA = "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
ACTIVE = [
    "EI-401", "EI-02", "EI-412", "EI-415", "EI-17",
    "EI-941", "EI-2738", "EI-407", "EI-417", "EI-935",
    "H24", "H25", "H23", "EI-2069",
]
REPLACEMENTS = [
    ("EI-20", "EI-941"), ("DISS-G", "EI-412"),
    ("EI-01", "EI-401"), ("EI-16", "EI-415"),
]
OTHER_EXCLUDED = {
    "EI-943", "EI-2259", "EI-2058", "H05", "EI-2072", "EI-2074",
}
RATE_HASHES = {
    "EI-941": "ca10a223d631e04a84464649bac96ba3c7ee4ca157a1127376e04b66781e2adc",
    "EI-412": "53bfaf78997b1992a5e9d34c014976b3a451ea2198b2acb2ed15505caadb1137",
    "EI-401": "185a102beb38d5a7a91846c69933b3f4b43e9c31dc0d57d1c5fae496206782ff",
    "EI-415": "9108838e43298185e71679d2fff09c74c5c601ed3ebbaa3ba02548a374db8c64",
    "EI-2069": "5eba74c1870e0635a3e316e143961e9f04e259675ddad00fd8653de28980644a",
    "EI-2738": "1896afa96f8865a0895fd4a8ae921fd89d3964f8782495331faae9e68c4c250d",
}
ARTIFACTS = {
    "400W": (
        13447489692,
        "df41ef2860d56b728082fd1fd7e7d3f498bc5b389bb94f5451e11576dd6a27cb",
        "5c9e29d4302a9797ef8219954e48a3ac05bf9fb824e5b665a652d8ef23b290ff",
        "8e5fe7e57dc11bfd9f6afa13a6e886e0891b4e07597a7849f703652d4ce26ea8",
    ),
    "1000W": (
        13448891366,
        "cf43e346d4496c9bcca8e50ec09a7cdac83b15ab26a15d4b5c1a8a72ecec91cf",
        "25f50f6252786d222443dcc949d644b02399ba21ee9912f6799c0bee78ea8908",
        "85196226b3e9f1b3e417f6c313615945b1a6caa393800698d9b82695714289ae",
    ),
}


def read_current() -> dict:
    current = json.loads((BASE / "current_reaction_base.json").read_text())
    assert current["schema_version"] == "oxygen_icp_research_reaction_base_v1"
    return current


def test_research_authority_and_holds() -> None:
    b = read_current()
    assert b["base_id"] == "oxygen-icp-h23-ei941-ei412-ei401-ei415-14ch-20261105"
    assert b["designation"] == "CURRENT_WORKING_REACTION_BASE"
    assert b["acceptance"] == "SCIENCE_HOLD"
    assert b["replay_policy"]["science_acceptance_must_remain"] == "HOLD"
    for claim in (
        "production chemistry acceptance", "scientific validation",
        "canonical Oxygen25/Issue419 reaction registry",
    ):
        assert claim in b["authority_boundary"]["not_promoted"]
    assert b["chemistry"]["no_automated_production_promotion"] is True
    assert b["authority_boundary"]["EI2069_removal_experiment_is_not_in_this_base"] is True


def test_exact_inventory_and_four_exclusive_replacements() -> None:
    b = read_current()
    chem = b["chemistry"]
    assert chem["active_channels"] == ACTIVE
    assert chem["active_channel_count"] == len(set(ACTIVE)) == 14
    assert chem["EI2069_active"] is True
    assert chem["EI943_active"] is False
    assert chem["EI2738_rate_mode"] == (
        "MCS_24case_derived_lookup_with_analytical_tails_provisional"
    )
    assert chem["explicit_replacements"] == [
        {"removed": removed, "added": added, "parallel_use_prohibited": True}
        for removed, added in REPLACEMENTS
    ]
    excluded = set(chem["excluded_parent_channels"])
    assert OTHER_EXCLUDED.issubset(excluded)
    assert excluded.isdisjoint(ACTIVE)
    for removed, added in REPLACEMENTS:
        assert removed in excluded and removed not in ACTIVE
        assert added in ACTIVE
    assert b["authority_boundary"]["four_exclusive_replacements_in_this_base"] is True
    assert b["authority_boundary"]["only_chemistry_change_from_predecessor"] == (
        "EI-16 -> EI-415, exclusive replacement"
    )
    assert b["authority_boundary"]["predecessor_14ch_run_id"] == 42047760912


def test_exact_native_run_evidence_and_source_pin() -> None:
    b = read_current()
    src = b["source"]
    assert src["immutable_verified_harness_sha"] == SOURCE_SHA
    assert src["reference_branch"] == (
        "base/oxygen-icp-14ch-ei941-ei412-ei401-ei415-20261105"
    )
    assert src["physics_app_pinned_sha"] == PHYSICS_SHA
    assert src["fixed_initial_eedf_sha256"] == EEDF_SHA
    assert src["workflow"] == (
        ".github/workflows/oxygen-h23-ei941-ei412-ei401-ei415-replaces-ei16-14ch-400-1000w-100us.yml"
    )
    assert src["action_run"].endswith("/42049066748")
    o = b["operating_conditions"]
    assert o["power_W"] == [400, 1000]
    assert o["end_time_s"] == 1e-4
    assert o["expected_native_timestep_count"] == 460
    assert o["recorded_csv_time_count"] == 461
    assert o["neutral_inlet_sccm"] == 200
    assert o["neutral_wall_sticking"] == 1
    assert o["native_initialization"] == "fresh_not_restarted"
    assert o["transport_eedf_sha256"] == EEDF_SHA
    for power, (artifact_id, zip_sha, run_sha, input_sha) in ARTIFACTS.items():
        actual = b["verified_runs"][power]
        assert actual["run_id"] == 42049066748
        assert actual["artifact_id"] == artifact_id
        assert actual["native_checkpoint_verified"] is True
        assert actual["native_P0_P4_pass"] is True
        assert actual["verified_endpoint_s"] == 1e-4
        assert actual["native_steps"] == 460
        assert power in actual["artifact_name"]
        assert actual["artifact_zip_sha256"] == zip_sha
        assert actual["native_run_archive_sha256"] == run_sha
        assert actual["native_inputs_archive_sha256"] == input_sha
        assert abs(actual["last_rf_power_W"] - int(power[:-1])) < 5.0


def test_rate_material_is_private_and_science_provisional() -> None:
    b = read_current()
    rates = b["rate_provenance"]
    for name, expected in RATE_HASHES.items():
        assert rates[name]["sha256"] == expected
    for name in ("EI-941", "EI-412", "EI-401", "EI-415", "EI-2069"):
        assert rates[name]["private"] is True
        assert len(rates[name]["sha256"]) == 64
    assert rates["EI-2738"]["private"] is False
    assert rates["EI-2738"]["model_mapping_provisional"] is True
    assert rates["EI-941"]["electron_loss_eV"] == 13.62
    assert rates["EI-412"]["electron_loss_eV"] == 6.0
    assert rates["EI-401"]["electron_loss_eV"] == 0.0
    assert rates["EI-415"]["electron_loss_eV"] == 12.06
    assert rates["EI-2069"]["electron_loss_eV"] == 5.02
    assert {str(x.relative_to(BASE)) for x in BASE.rglob("*") if x.is_file()} == {
        "README.md",
        "current_reaction_base.json",
        str(HISTORY.relative_to(BASE)),
    }


def test_superseded_old_base_remains_accessible_and_frozen() -> None:
    b = read_current()
    old = json.loads(HISTORY.read_text())
    assert old["designation"] == "SUPERSEDED_WORKING_REACTION_BASE"
    assert old["acceptance"] == "SCIENCE_HOLD"
    assert old["source"]["immutable_verified_harness_sha"] == OLD_SOURCE_SHA
    assert old["verified_runs"]["400W"]["run_id"] == 42043664537
    assert old["verified_runs"]["1000W"]["run_id"] == 42043664537
    assert old["chemistry"]["active_channels"] == [
        "EI-01", "EI-02", "DISS-G", "EI-16", "EI-17",
        "EI-941", "EI-2738", "EI-407", "EI-417", "EI-935",
        "H24", "H25", "H23", "EI-2069",
    ]
    assert old["superseded_by_run_id"] == 42049066748
    assert old["superseded_by_base_id"] == b["base_id"]
    assert b["authority_boundary"]["prior_working_base_sha"] == OLD_SOURCE_SHA
    assert b["authority_boundary"]["prior_working_base_run_id"] == 42043664537
    assert b["authority_boundary"]["prior_working_base_snapshot"] == (
        "experiments/Issue395_powered_chemistry_ladder/research_baselines/"
        "history/oxygen-icp-h23-no943-mcs2738-ei2069-ei941-14ch-20261105.json"
    )


def test_documented_replay_and_hold() -> None:
    text = (BASE / "README.md").read_text()
    for marker in (
        "CURRENT_WORKING_REACTION_BASE", "SCIENCE_HOLD",
        "Run #42049066748", SOURCE_SHA,
        "Run #42043664537", OLD_SOURCE_SHA,
        "EI-415", "EI-401", "EI-412", "EI-941",
        "EI-01", "EI-16", "EI-20", "DISS-G",
        "EI-2069", "Issue #419",
    ):
        assert marker in text
