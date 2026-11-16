#!/usr/bin/env python3
"""Issue541 CORE four one-shots: exact-source replacement and retention guard.

A PASS is P0/CI source coverage only, not a Native P2 PASS nor workflow retirement.
"""
from __future__ import annotations
import argparse
import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "ci/baselines/issue541_core_four_retirement.json"
CI = ROOT / ".github/workflows/ci.yml"

REQUIRED_P0 = (
"tests/test_issue402_dd_plasma_boundary_json.py",
"tests/test_issue402_species_initial_density_pairs.py",
"tests/test_issue402_dd_json_fem_fvm_wiring.py",
"tests/test_issue402_species_transport_rule.py",
"tests/test_issue402_material_class_names.py",
"tests/test_issue402_s6_dd_review_package.py",
"tests/test_issue402_energy_poisson_auto_variables.py",
"tests/test_issue402_sccm_inlet_cpp.py",
"tests/test_issue402_sccm_inlet_flow.py",
"tests/test_issue402_species_initial_composition.py",
"tests/test_issue402_species_live_ic_inlet.py",
"tests/test_issue402_rate_coef_ideal_gas.py",
"tests/test_issue402_fem_electron_sheath_bc_retirement.py",
"tests/test_issue402_json_rate_unification.py",
"tests/test_electron_impact_rate_material_prefix.py",
"tests/test_issue402_no_legacy_material_registration.py",
"tests/test_issue402_reaction_reduction_p2_only.py",
"tests/test_issue402_retired_plasma_closures.py",
"tests/characterization/test_issue395_ei17_overlay.py",
"tests/characterization/test_issue192_s5r.py",
"tests/characterization/test_issue192_s5r_runtime.py",
)
P0_CHECKERS = (
"physics_app/ci/check_stage5_s5d_heavy_reactions.py --static",
"physics_app/ci/check_stage5_s5d_heavy_reactions.py --self-test",
"physics_app/ci/check_stage5_h05_runtime.py --static",
"physics_app/ci/check_stage5_s5r_assembly.py --static",
"physics_app/ci/check_stage5_s5r_assembly.py --self-test",
"physics_app/ci/audit_issue402_initial_composition_routes.py",
)
P2_MARKERS = (
"DD_JSON_BOUNDARY_NATIVE_P2_PASS_P3_NOT_RUN",
"ISSUE402_SCCM_STATIC_GAS_NATIVE_P2_PASS_P3_NOT_RUN",
"SPECIES_INITIAL_VOLUME_INLET_NATIVE_P2_PASS",
"FOUR_LIVE_Y_MATERIALS_FV_IC_AND_INLET_NATIVE_P2_PASS",
"SCCM_MUTATIONS_AND_DERIVED_OWNER_P2_PASS",
"JSON_SURFACE_RATE_NATIVE_P2_PASS",
"JSON_HEAVY_SURFACE_NATIVE_P2_PASS_P3_NOT_RUN",
"SCCM_STATIC_GAS_NATIVE_P1_PASS",
"JSON_RATE_NATIVE_P1_PASS",
)
ORIGINALS = (
"issue402-dd-json-boundary-p0-p2-once.yml",
"issue402-sccm-fixed-gas-p0-p2-once.yml",
"issue402-species-initial-composition-native-once.yml",
"issue402-species-live-ic-inlet-native-once.yml",
)

def check(manifest: dict, ci: str, native: str) -> None:
    assert manifest["schema"] == "issue541.core_four.retirement_contract.v1"
    assert manifest["science"] == "SCIENCE_HOLD"
    assert manifest["p3"] == "NOT_REQUESTED"
    assert manifest["ownership"] == "CORE_END_TO_END"
    assert manifest["replacement"]["native_runner"] == "physics_app/ci/run_issue541_core_four_native_p2.py"
    assert "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008" in manifest["replacement"]["required_build_base"]
    owners = manifest["workflows"]
    assert len(owners) == len(ORIGINALS)
    assert {x["path"].rsplit("/", 1)[-1] for x in owners} == set(ORIGINALS)
    for row in owners:
        assert re.fullmatch("[0-9a-f]{40}", row["original_blob"])
        assert row["scope"] == "P0_P1_P2_ONLY"
        assert row["original_p3"] == "NOT_RUN"
        assert row["retirement"] in ("KEEP_HOLD", "RETIRED_VERIFIED", "STAGED_DELETE_KEEP_HOLD_INTEGRATION")
        assert row["required_marker"] in P2_MARKERS
        assert row["reason"]
        source = ROOT / row["path"]
        if row["retirement"] == "KEEP_HOLD":
            assert source.is_file(), "HOLD_WORKFLOW_MISSING:" + row["path"]
        else:
            assert not source.exists(), "PREMATURE_RETIREMENT:" + row["path"]
            assert not row["branch_present_at_2026_11_15"], "HISTORIC_BRANCH_STILL_LIVE"
            assert row["caller_observation"] == "HISTORICAL_PUSH_BRANCH_NOT_FOUND"
            if row["retirement"] == "STAGED_DELETE_KEEP_HOLD_INTEGRATION":
                assert row.get("rollback_original_blob") == row["original_blob"], "WAVE1D_ROLLBACK_BLOB_MISSING"
                assert row.get("wave1d_caller_zero") == "UNVERIFIED", "WAVE1D_CALLER_ZERO_FALSE_PROOF"
                assert row.get("wave1d_integration") == "HOLD", "WAVE1D_INTEGRATION_FALSE_PASS"
        hist = row["original_success"]
        assert hist["run_id"] > 0 and hist["artifact_id"] > 0
        assert re.fullmatch("[0-9a-f]{40}", hist["source_sha"])
        assert re.fullmatch("[0-9a-f]{64}", hist["zip_sha256"])
        assert hist["zip_bytes"] > 1000 and "2026-12" in hist["expires_at"]
        backup = row["independent_backup"]
        assert backup["readback_sha256"] == hist["zip_sha256"]
        assert backup["readback_bytes"] == hist["zip_bytes"]
        assert backup["status"] == "PRIVATE_OWNER_ONLY_SHA256_VERIFIED"
        assert backup["url"].startswith("https://drive.google.com/file/d/")
    assert manifest["backup"]["visibility"] == "OWNER_ONLY_NOT_SHARED"
    assert manifest["backup"]["readback"] == "SHA256_AND_SIZE_VERIFIED"
    assert manifest["backup"]["permanent_worm"] == "NOT_PROVEN"
    # A completed run proves only its *exact* source SHA and each individual job.
    # A newer branch HEAD needs a new Actions run; green subjobs are not CI PASS.
    replacement = manifest["replacement"]
    receipt = replacement["verification_receipt"]
    assert receipt["claim"] == "PRIOR_COMPLETED_EXACT_HEAD_P0_P1_P2_ONLY"
    assert receipt["repository"] == "HyungseonSong-plasma/moose-test-repo"
    assert receipt["pr_number"] == 553
    assert re.fullmatch(r"[0-9a-f]{40}", replacement["source_verified_head"])
    assert receipt["head_sha"] == replacement["source_verified_head"], "EVIDENCE_HEAD_MISMATCH"
    assert receipt["workflow_run_id"] == replacement["source_verified_run"], "EVIDENCE_RUN_MISMATCH"
    assert receipt["workflow_run_id"] > 0 and receipt["run_attempt"] >= 1
    assert receipt["workflow_name"] == "Repository CI"
    assert receipt["event"] == "pull_request"
    assert receipt["run_conclusion"] == "failure", "GLOBAL_CI_FALSE_PASS"
    assert receipt["p3"] == "NOT_RUN" and receipt["science"] == "SCIENCE_HOLD"
    assert receipt["freshness_policy"] == "NEW_HEAD_REQUIRES_NEW_EXACT_HEAD_RUN_AND_JOB_RECEIPTS"
    p0_receipt, native_receipt = receipt["p0"], receipt["native_p1_p2"]
    assert p0_receipt["job_name"] == "Issue541 CORE four boundary SCCM composition inlet P0 (no Native)"
    assert native_receipt["job_name"] == "Issue541 CORE four native source-bound P1 P2 (no P3)"
    assert p0_receipt["conclusion"] == native_receipt["conclusion"] == "success"
    assert {p0_receipt["job_id"], native_receipt["job_id"]} and p0_receipt["job_id"] != native_receipt["job_id"]
    assert all(x["job_id"] > 0 and x["artifact_id"] > 0 for x in (p0_receipt, native_receipt))
    assert p0_receipt["artifact_name"] == f"issue541-core-four-p0-{receipt['workflow_run_id']}"
    assert native_receipt["artifact_name"] == f"issue541-core-four-native-{receipt['workflow_run_id']}"
    others = receipt["other_gates"]
    assert set(others) == {"validate", "plasma_native_regression"}
    assert others["validate"]["conclusion"] == others["plasma_native_regression"]["conclusion"] == "failure"
    assert others["validate"]["reason"] == "WORKFLOW_SURFACE_GUARD"
    assert others["plasma_native_regression"]["reason"] == "PUBLIC_S6_417_941_P2_HOLD"
    assert all(x["job_id"] > 0 for x in others.values())
    assert len({p0_receipt["job_id"], native_receipt["job_id"], *(x["job_id"] for x in others.values())}) == 4
    assert sum(x["branch_present_at_2026_11_15"] for x in owners) == 1
    assert ci.count("  issue402_core_four_p0:") == 1
    assert ci.count("  issue402_core_four_native_p2:") == 1
    start = ci.index("  issue402_core_four_p0:")
    end = ci.index("  issue402_core_four_native_p2:")
    p0, p2 = ci[start:end], ci[end:]
    for path in REQUIRED_P0:
        assert path in p0, "P0_TARGET_MISSING:" + path
    for command in P0_CHECKERS:
        assert command in p0, "CHECKER_MISSING:" + command
    assert "issue541_core_four_contract.py --self-test" in p0
    assert "issue541_core_four_contract.py --check" in p0
    assert "github.event.pull_request.head.sha" in p0
    assert "github.event.pull_request.head.sha" in p2
    assert "make -C physics_app -j2" in p2
    assert "physics_app/ci/run_issue541_core_four_native_p2.py" in p2
    assert "P3=NOT_RUN" in p2 and "SCIENCE_HOLD" in p2
    for marker in P2_MARKERS:
        assert marker in native, "NATIVE_MARKER_MISSING:" + marker
    for required in (
        "check_issue402_dd_json_plasma_boundary_p2.py",
        "check_issue402_species_initial_composition_p2.py",
        "json_species_live_all4_p2.i",
        "plasma_direct_existing_materials_smoke.i",
        "dd_plasma_boundary_legacy_p2.i",
        "dd_plasma_boundary_json_physics_auto_p2.i",
    ):
        assert required in native, "NATIVE_OBLIGATION_MISSING:" + required

def self_test(m: dict, ci: str, native: str):
    check(m, ci, native)
    for label, alternate in (
        ("P0_TARGET", ci.replace("tests/test_issue402_species_live_ic_inlet.py", "tests/REMOVED.py", 1)),
        ("NATIVE_JOB", ci.replace("  issue402_core_four_native_p2:", "  BROKEN_CORE_NATIVE:", 1)),
        ("NATIVE_P2", native.replace("DD_JSON_BOUNDARY_NATIVE_P2_PASS_P3_NOT_RUN", "MISSING_DD_P2", 1)),
        ("P3_PROMOTION", ci.replace("echo \"P3=NOT_RUN; SCIENCE_HOLD\"", "echo \"P3=PASS; SCIENCE_ACCEPTED\"", 1)),
    ):
        try:
            check(m, alternate if label in ("P0_TARGET", "NATIVE_JOB", "P3_PROMOTION") else ci,
                  alternate if label == "NATIVE_P2" else native)
        except AssertionError:
            pass
        else:
            raise AssertionError("MUTATION_NOT_DETECTED:" + label)
    for label, mutator in (
        ("ARTIFACT_SHA", lambda x: x["workflows"][0].update(original_blob="bad")),
        ("PREMATURE_DELETE", lambda x: x["workflows"][0].update(retirement="RETIRED_VERIFIED")),
        ("SCIENCE_PROMOTION", lambda x: x.update(science="ACCEPTED")),
        ("BACKUP_HASH_TAMPER", lambda x: x["workflows"][0]["independent_backup"].update(readback_sha256="0"*64)),
        ("BACKUP_PUBLIC", lambda x: x["backup"].update(visibility="PUBLIC")),
        ("WAVE1D_STAGED_FALSE_CALLER_ZERO", lambda x: x["workflows"][1].update(wave1d_caller_zero="VERIFIED")),
        ("WAVE1D_STAGED_MISSING_ROLLBACK", lambda x: x["workflows"][1].update(rollback_original_blob="0" * 40)),
    ):
        bad = copy.deepcopy(m)
        mutator(bad)
        try:
            check(bad, ci, native)
        except AssertionError:
            pass
        else:
            raise AssertionError("MUTATION_NOT_DETECTED:" + label)
    # Independent mutations of the external Actions receipt must fail closed.
    for label, mutator in (
        ("HEAD_MISMATCH", lambda x: x["replacement"]["verification_receipt"].update(head_sha="0" * 40)),
        ("RUN_MISMATCH", lambda x: x["replacement"]["verification_receipt"].update(workflow_run_id=1)),
        ("EVENT_MISMATCH", lambda x: x["replacement"]["verification_receipt"].update(event="push")),
        ("P0_FALSE_PASS", lambda x: x["replacement"]["verification_receipt"]["p0"].update(conclusion="failure")),
        ("P2_FALSE_PASS", lambda x: x["replacement"]["verification_receipt"]["native_p1_p2"].update(conclusion="failure")),
        ("ARTIFACT_MISSING", lambda x: x["replacement"]["verification_receipt"]["native_p1_p2"].update(artifact_id=0)),
        ("GLOBAL_CI_FALSE_PASS", lambda x: x["replacement"]["verification_receipt"].update(run_conclusion="success")),
        ("GLOBAL_GATE_HIDDEN", lambda x: x["replacement"]["verification_receipt"]["other_gates"].pop("validate")),
        ("FRESHNESS_PROMOTION", lambda x: x["replacement"]["verification_receipt"].update(claim="CURRENT_HEAD_FULLY_VERIFIED")),
    ):
        bad = copy.deepcopy(m)
        mutator(bad)
        try:
            check(bad, ci, native)
        except AssertionError:
            pass
        else:
            raise AssertionError("MUTATION_NOT_DETECTED:EVIDENCE_" + label)
    print("ISSUE541_CORE_FOUR_MUTATION_SELF_TEST=PASS")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.check and not args.self_test:
        parser.error("--check or --self-test required")
    m = json.loads(MANIFEST.read_text())
    ci = CI.read_text()
    native = (ROOT / m["replacement"]["native_runner"]).read_text()
    if args.self_test:
        self_test(m, ci, native)
    if args.check:
        check(m, ci, native)
        import os
        observed_head = os.environ.get("EXPECTED_HEAD")
        evidence_head = m["replacement"]["source_verified_head"]
        if observed_head:
            assert re.fullmatch(r"[0-9a-f]{40}", observed_head), "EXPECTED_HEAD_INVALID"
        scope = ("EXACT_SOURCE_MATCH_ONLY" if observed_head == evidence_head
                 else "PRIOR_VERIFIED_HEAD_REQUIRES_FRESH_CI")
        print("ISSUE541_CORE_FOUR_SOURCE_CONTRACT=PASS; P3=NOT_RUN; SCIENCE_HOLD; "
              f"EVIDENCE_HEAD={evidence_head}; HEAD_LINEAGE={scope}")

if __name__ == "__main__":
    main()
