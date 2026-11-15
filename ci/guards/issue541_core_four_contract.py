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
        assert row["retirement"] == "KEEP_HOLD"  # change only with new evidence, never automatically
        assert row["required_marker"] in P2_MARKERS
        assert row["reason"]
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
    ):
        bad = copy.deepcopy(m)
        mutator(bad)
        try:
            check(bad, ci, native)
        except AssertionError:
            pass
        else:
            raise AssertionError("MUTATION_NOT_DETECTED:" + label)
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
        print("ISSUE541_CORE_FOUR_SOURCE_CONTRACT=PASS; P3=NOT_RUN; SCIENCE_HOLD")

if __name__ == "__main__":
    main()
