"""Issue #535 S6 full 400 W/100 us terminal replay receipt, not a science-parity checker.

The former issue535_postrelease_eight_hold_gate manifest and tests remain
immutable snapshots of the earlier 9/10 review and running dispatch.
This independently source-bound final receipt supersedes only the S6
*operational workflow retirement* disposition after user visual review.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "ci/baselines/issue535_s6_full_100us_retirement_closure_20261117.json"
PREVIOUS = ROOT / "ci/baselines/issue535_postrelease_eight_hold_gate_20261116.json"
SOURCE = "8263fbc1801f213b98183ba4876299041cd01dac"
RUN = 44050874900
EXPECTED = {
    "417": {
        "job_id": 133928069072,
        "artifact_id": 14327600496,
        "artifact_zip_bytes": 98686794,
        "artifact_zip_sha256": "85569e10170d3825a051f9dd5a6f8c24ee498122ae20874b9c20325cfbda98f1",
        "exodus_sha256": "af731e1c5c5c91c323d335f3d71330c1d429498f91d9984cc187321970d7aa32",
        "csv_sha256": "4591242b0f80ef1e4ae2bbabec41343cbb4bc17d6e407cccd00eeb0ce63e2fe8",
        "horizontal_png_sha256": "bcb82ddfb56b29411fa03f1b5cca10ea19ecbc4994ed3339b1ea29b298b187e6",
        "vertical_png_sha256": "c118e0bfd17202c02bede00db726a1b8f975e799f175ca288fbd1f9a68031fd5",
        "metrics_json_sha256": "0847b1ef31f8e93b5c60af1eab6040aca70c4f308438601573f50bb7d789118e",
        "expires_at_utc": "2027-01-01T12:08:39Z",
        "horizontal_relative_l2": 0.06848464101507847,
        "vertical_relative_l2": 0.03930191280350551,
        "native_peak_over_reference_peak": 1.0224145157537288,
    },
    "941": {
        "job_id": 133928068701,
        "artifact_id": 14333842379,
        "artifact_zip_bytes": 98635771,
        "artifact_zip_sha256": "e1a11b9125db5c8063dcf075da6b4c3e2f61c8e1b725ba54bdf52e67f8d14b23",
        "exodus_sha256": "1abed7662d208da9bb919d738adf5feabd63cfe7fac359d4dce495805396b83f",
        "csv_sha256": "c8daa7ed6d09156f87141eefe4b4564ee0b87fbfdd5d9c894324fff6185ef117",
        "horizontal_png_sha256": "83baec401b636600bdd58a785fcccf0257424055d1a532eab126359ad15c3480",
        "vertical_png_sha256": "c3667334d385de8c1848720b35d2d9f6278841bed17f3e6b5e3ef990066a9fe7",
        "metrics_json_sha256": "cd2d57f5b646b42c2dab91c1d21ae144461e5e8f6b7d477a3beff10921ee6774",
        "expires_at_utc": "2027-01-01T13:46:26Z",
        "horizontal_relative_l2": 0.06904315414600136,
        "vertical_relative_l2": 0.039490758948861567,
        "native_peak_over_reference_peak": 1.0199766679131463,
    },
}


def _read() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def _check(data: dict) -> None:
    assert data["schema"] == "issue535.s6_full_100us_retirement_closure.v1"
    assert data["repository"] == "HyungseonSong-plasma/moose-test-repo"
    old = data["supersedes_current_decision"]
    assert old["previous_manifest"] == PREVIOUS.relative_to(ROOT).as_posix()
    assert old["previous_manifest_is_historical_snapshot"] is True
    assert old["previous_main"] == "fb77673d7bbbbeb389549929a8f57724c703ff7e"
    assert (old["previous_wave1_retired_verified"], old["previous_wave1_keep_hold"],
            old["previous_S6_disposition"]) == (9, 1, "KEEP_HOLD")

    approval = data["operator_approval"]
    assert approval["caller_risk_and_owner_mutable_drive_issue535_comment"] == 6943043495
    assert approval["result_equivalence_user_chat_date_utc"] == "2026-11-17"
    assert approval["result_equivalence_verdict"] == (
        "ACCEPTED_VISUAL_COMPARISON_S6_417_941_400W_100US_ELECTRON_DENSITY")
    assert approval["accepted_scope"] == (
        "HISTORICAL_HYBRID_S6_TWO_CASES_P3_OUTPUT_AND_OPERATOR_VISUAL_DENSITY_EQUIVALENCE")
    assert approval["reference_timestamp_unknown_acknowledged"] is True
    assert approval["reference_coordinates_assumed_acknowledged"] is True
    assert approval["no_automatic_science_or_native_free_cutover_promotion"] is True
    assert approval["large_p3_zip_drive_upload_required"] is False
    assert approval["large_artifact_retention"] == (
        "GITHUB_ACTIONS_UNTIL_STATED_EXPIRY_OPERATOR_ACCEPTS_NO_DRIVE_MIRROR")
    assert approval["existing_original_failed_and_bounded_success_independent_drive_archives_unchanged"] is True
    assert approval["worm_object_lock_claimed"] is False

    workflow = data["workflow"]
    assert workflow["original_path"] == ".github/workflows/issue402-hybrid-json-s6-p3-p4-once.yml"
    assert workflow["original_blob_sha"] == "485439a723584ca5bbc8632a86c53574b0b1eb9a"
    assert workflow["non_executable_archive_path"] == (
        "docs/development/archive/issue402-hybrid-json-s6-p3-p4-once.yml.txt")
    assert workflow["replacement_path"] == ".github/workflows/issue541-arch-s6-p3-p4-replay.yml"
    assert workflow["replacement_blob_sha"] == "6c673628eac4693abe0d74b04fc31578a39b3971"
    assert workflow["only_manual_dispatch"] is True
    assert workflow["source_sha_checked_pre_checkout"] is True
    assert workflow["original_legacy_yaml_not_reactivated"] is True
    assert workflow["approval_input"] == "ISSUE541_S6_400W_100US_BOTH_CASES_APPROVED"

    run = data["execution"]
    assert (run["run_id"], run["attempt"], run["event"], run["head_branch"]) == (
        RUN, 1, "workflow_dispatch", "main")
    assert run["head_sha"] == SOURCE
    assert run["run_status"] == "completed" and run["run_conclusion"] == "success"
    assert run["completed_at_utc"] == "2026-11-17T13:46:34Z"
    assert run["case_matrix"] == ["417", "941"]
    assert run["power_w"] == 400 and run["duration_us"] == 100
    assert run["provenance"] == (
        "ACTUAL_GITHUB_RUN_AND_DOWNLOADED_ARTIFACT_BYTES_SHA256_CRC_AND_STATUS_JSON")
    assert run["p4_not_promoted"] is True
    assert set(run["cases"]) == set(EXPECTED)
    assert len({v["job_id"] for v in run["cases"].values()}) == 2
    assert len({v["artifact_id"] for v in run["cases"].values()}) == 2

    for case, expected in EXPECTED.items():
        record = run["cases"][case]
        for key, value in expected.items():
            assert record[key] == value, "S6_EVIDENCE_TAMPERED:" + case + ":" + key
        assert record["case"] == case
        assert record["run_status"] == "completed" and record["job_conclusion"] == "success"
        assert (record["P0"], record["P1"], record["P2"], record["P3"], record["P4"]) == (
            "PASS", "PASS_SOURCE_BOUND_BINARY", "PASS", "PASS", "DIAGNOSTIC_ONLY")
        assert record["native_time_us"] == 100 and record["frames"] == 461
        assert record["artifact_zip_crc"] == "PASS_15_MEMBERS"
        assert record["artifact_drive_upload"] == "NOT_REQUESTED_LARGE_ARTIFACT"
        assert record["reference_timestamp"] == "UNKNOWN"
        assert record["reference_coordinates"] == "ASSUMED_R_0_TO_25_Z_0_TO_44_CM"
        for field in ("artifact_zip_sha256", "exodus_sha256", "csv_sha256",
                      "horizontal_png_sha256", "vertical_png_sha256", "metrics_json_sha256"):
            assert re.fullmatch(r"[0-9a-f]{64}", record[field])

    reference = data["independent_reference"]
    assert reference["comparison_role"] == (
        "DIAGNOSTIC_PLUS_OPERATOR_VISUAL_EQUIVALENCE_APPROVAL")
    assert reference["reference_timestamp"] == "UNKNOWN"
    assert reference["coordinates"] == "ASSUMED_R_0_TO_25_Z_0_TO_44_CM"
    assert reference["quantitative_threshold_predeclared"] is False
    assert reference["do_not_claim_mathematical_or_regime_wide_parity"] is True

    conclusion = data["final_disposition"]
    assert conclusion["original_S6_workflow"] == "RETIRED_VERIFIED"
    assert conclusion["scope"] == (
        "OPERATIONAL_RETIREMENT_OF_ORIGINAL_S6_P3_WORKFLOW_WITH_SOURCE_BOUND_FULL_417_941_REPLAY")
    assert (conclusion["wave1_originals_total"], conclusion["wave1_retired_verified"],
            conclusion["wave1_keep_hold"]) == (10, 10, 0)
    assert conclusion["arch_DD"] == "RETIRED_VERIFIED"
    assert conclusion["arch_S6"] == "RETIRED_VERIFIED"
    assert conclusion["source_p3"] == "PASS_BOTH_100US"
    assert conclusion["operator_electron_density_equivalence"] == "ACCEPTED_SCOPED"
    assert conclusion["separate_science_status"] == "SCIENCE_HOLD_FOR_BROADER_SCIENTIFIC_CLAIMS"
    assert conclusion["p4"] == "DIAGNOSTIC_ONLY"
    assert conclusion["native_free_ion_poisson_rf_cutover"] == "NOT_ESTABLISHED"
    assert conclusion["issue402_parent"] == "OPEN_UNTIL_INDEPENDENT_CUTOVER_GATES"
    assert conclusion["no_new_p3_dispatch"] is True
    assert conclusion["original_failed_run_history_preserved"] is True


def test_final_receipt_with_scoped_operator_acceptance():
    _check(_read())


def test_old_hold_snapshot_preserved_not_rewritten():
    old = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    s6 = next(x for x in old["cases"] if x["id"] == "S6")
    assert s6["formal_disposition"] == "KEEP_HOLD"
    assert old["arch_retirement_outcome"]["current_proposed_wave1_retired"] == 9
    assert old["arch_p3_dispatch_approval"]["P3_full_scope_executed"] is False
    assert old["arch_p3_dispatch_approval"]["run_id"] == RUN


def test_original_s6_is_archived_bit_identically_and_not_executable():
    d = _read()["workflow"]
    assert not (ROOT / d["original_path"]).exists()
    blob = (ROOT / d["non_executable_archive_path"]).read_bytes()
    assert hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest() == (
        d["original_blob_sha"])
    replay = (ROOT / d["replacement_path"]).read_text(encoding="utf-8")
    assert "workflow_dispatch" in replay
    assert d["approval_input"] in replay
    assert 'test "$REQUESTED_SHA" = "$GITHUB_SHA"' in replay
    assert "SCIENCE_HOLD" in replay


@pytest.mark.parametrize("path,value", [
    (("execution", "run_conclusion"), "failure"),
    (("execution", "head_sha"), "0" * 40),
    (("execution", "case_matrix"), ["417"]),
    (("execution", "cases", "417", "P3"), "NOT_RUN"),
    (("execution", "cases", "941", "job_id"), 133928069072),
    (("execution", "cases", "941", "artifact_zip_sha256"), "0" * 64),
    (("execution", "cases", "417", "horizontal_png_sha256"), "0" * 64),
    (("execution", "cases", "941", "native_time_us"), 3),
    (("execution", "cases", "417", "artifact_drive_upload"), "DRIVE_BACKUP_PROVEN"),
    (("operator_approval", "reference_timestamp_unknown_acknowledged"), False),
    (("operator_approval", "large_p3_zip_drive_upload_required"), True),
    (("independent_reference", "reference_timestamp"), "100US_KNOWN"),
    (("independent_reference", "quantitative_threshold_predeclared"), True),
    (("final_disposition", "separate_science_status"), "SCIENCE_ACCEPTED"),
    (("final_disposition", "p4"), "PASS"),
    (("final_disposition", "native_free_ion_poisson_rf_cutover"), "PASS"),
    (("final_disposition", "wave1_retired_verified"), 9),
])
def test_forged_or_out_of_scope_receipt_rejected(path, value):
    doc = copy.deepcopy(_read())
    entry = doc
    for key in path[:-1]:
        entry = entry[key]
    entry[path[-1]] = value
    with pytest.raises(AssertionError):
        _check(doc)
