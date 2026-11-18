#!/usr/bin/env python3
"""Fail-closed separation of historical Hybrid failures from New-only P2.

No CI bypass, no input rewrite, no protected rate payload, no science promotion.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECEIPT = ROOT / "reports/issue633/s6-417-941-hybrid-newonly-separated-native-repro-20261118.json"
CASES = ("417", "941")
REQUIRED_LANES = {
    "HISTORICAL_PUBLIC_B",
    "HISTORICAL_PUBLIC_D",
    "HISTORICAL_FLOW_D_BASE",
    "HISTORICAL_ARCH_HYBRID",
    "PRODUCTION_NEWONLY",
}
OLD_FAILURE = "FAIL_EXPECTED_P05_NI_TIME"
NEW_PASS = "PASS_NATIVE_CHECK_INPUT"

def check_receipt(r: dict) -> None:
    assert r["schema"] == "issue633.s6_hybrid_newonly_route_separation.v1"
    assert r["authoritative_source"]["head"] == "52067302d16074592503d0ef6b903cc344f55a08"
    assert r["authoritative_source"]["source_merges"] is False
    assert r["authoritative_source"]["protected_rate_files_included"] is False
    assert set(r["separated_lanes"]) == REQUIRED_LANES
    for case in CASES:
        hybrid = r["separated_lanes"]["HISTORICAL_ARCH_HYBRID"]["case_results"]
        newonly = r["separated_lanes"]["PRODUCTION_NEWONLY"]["case_results"]
        public_b = r["separated_lanes"]["HISTORICAL_PUBLIC_B"]["case_results"]
        public_d = r["separated_lanes"]["HISTORICAL_PUBLIC_D"]["case_results"]
        assert hybrid[case] == OLD_FAILURE
        assert newonly[case] == NEW_PASS
        assert public_b[case] == "PASS_SYNTAX_OK"
        assert public_d[case] == "FAIL_MISSING_FEM_E_TRANSPORT_JSON"
        assert r["arch_native_receipts"][case]["exit_code"] != 0
        assert r["newonly_native_receipts"][case]["exit_code"] == 0
        assert r["newonly_native_receipts"][case]["syntax_ok"] is True
        for key in ("arch", "newonly"):
            evidence = (r["arch_native_receipts"] if key=="arch" else
                        r["newonly_native_receipts"])[case]
            assert len(evidence["log_sha256"]) == 64
    flow = r["separated_lanes"]["HISTORICAL_FLOW_D_BASE"]["case_results"]
    assert flow == {"417":"FAIL_MISSING_FEM_E_TRANSPORT_JSON",
                    "941":"NOT_RUN_EARLY_STOP"}
    assert all(len(x["zip_sha256"]) == 64 for x in r["verified_artifacts"].values())
    policy = r["strict_contract"]
    for key in ("hybrid_failure_never_counts_as_newonly_success",
                "historical_hybrid_failure_retained_as_failure_in_original_job",
                "no_continue_on_error_or_auto_ci_skip","no_P05_waiver",
                "no_implicit_BC_or_transport_substitution",
                "newonly_native_success_requires_actual_417_941_clean_exit_and_SHA",
                "SCIENCE_HOLD"):
        assert policy[key] is True, "FAIL_CLOSED_POLICY_"+key
    assert policy["global_CI_routing_update"].startswith("NOT_APPLIED")
    assert policy["P3_P4"] == "NOT_RUN"
    assert r["verdict"].endswith("COMMON_CI_NOT_YET_CHANGED")

def negative_tests(receipt: dict) -> None:
    mutations = [
        ("HYBRID_FALSE_PASS", ("separated_lanes","HISTORICAL_ARCH_HYBRID","case_results","417"), NEW_PASS),
        ("NEWONLY_FALSE_PASS", ("separated_lanes","PRODUCTION_NEWONLY","case_results","941"), OLD_FAILURE),
        ("PUBLIC_D_FALSE_PASS", ("separated_lanes","HISTORICAL_PUBLIC_D","case_results","417"), "PASS_SYNTAX_OK"),
        ("MISSING_FLOW_CASE", ("separated_lanes","HISTORICAL_FLOW_D_BASE","case_results","941"), "PASS"),
        ("WAIVED_P05", ("strict_contract","no_P05_waiver"), False),
        ("HIDDEN_LEGACY_RED", ("strict_contract","historical_hybrid_failure_retained_as_failure_in_original_job"), False),
        ("SKIPPED_GLOBAL_CI", ("strict_contract","no_continue_on_error_or_auto_ci_skip"), False),
        ("FAKE_MERGED_ROUTE", ("strict_contract","global_CI_routing_update"), "MERGED"),
        ("SCIENCE_PROMOTED", ("strict_contract","SCIENCE_HOLD"), False),
        ("MISSING_941_ERROR", ("arch_native_receipts","941","exit_code"), 0),
    ]
    for label, path, bad in mutations:
        fake=copy.deepcopy(receipt)
        node=fake
        for key in path[:-1]: node=node[key]
        node[path[-1]]=bad
        try:
            check_receipt(fake)
        except (AssertionError,KeyError,TypeError):
            continue
        raise AssertionError("FAIL_OPEN_MUTATION_"+label)
    print("S6_LANE_FAIL_CLOSED_MUTATIONS=10_OF_10_PASS")

def check_source_workflows() -> None:
    ci=(ROOT/".github/workflows/ci.yml").read_bytes()
    template=(ROOT/"ci/workflow_templates/general-ci.yml").read_bytes()
    assert ci==template, "CI_TEMPLATE_DIVERGED"
    text=ci.decode()
    assert "  issue541_arch_s6_hybrid_native_p2:" in text
    assert "  plasma_native_regression:" in text
    assert "run_public_option_s6_p2.sh" in text
    assert "issue541_arch_s6_native_p2_only.py" in text
    assert "continue-on-error: true" not in text
    ion=(ROOT/".github/workflows/ion-fvm-hybrid-staged-dt.yml").read_text()
    assert "New-only S6 source P0" in ion
    assert "150/200-step callers are retired" in ion
    print("S6_EXISTING_CI_HISTORICAL_FAILURE_NOT_MASKED=PASS")

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--check",action="store_true")
    a=p.parse_args()
    r=json.loads(RECEIPT.read_text())
    check_receipt(r)
    if a.self_test: negative_tests(r)
    if a.check: check_source_workflows()
    print("S6_HYBRID_NEWONLY_LANE_CONTRACT=PASS_EVIDENCE_SCOPE_ONLY")
    return 0
if __name__=="__main__": raise SystemExit(main())
