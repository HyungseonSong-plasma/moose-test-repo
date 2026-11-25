#!/usr/bin/env python3
"""Fail-closed #816 retirement: old FLOW D-base and ARCH Hybrid positive P2."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FLOW = ".github/workflows/issue402-flow-native-p2-regression.yml"
NATIVE = ".github/workflows/physics-native-ci.yml"
P6_MANUAL = ".github/workflows/physics-p6-validation.yml"
CONTRACT = "ci/contracts/repository_ci_scope_v1.json"
ARCHIVED = {
    "ci/baselines/issue541_group_a2_flow_retirement.json": "e9d5af65d912e12022ca1844bcafb4ea7d561b76",
    "ci/baselines/issue541_group_b_flow_reaction_retirement.json": "a4c56dc057b834367dc5d6ae96af89f83c0f9724",
    "ci/baselines/issue541_arch_s6_p2_independent_closure_20261116.json": "5c0801d7fc898d8faf426a3fd4a1fd5435c77073",
    "ci/guards/issue541_arch_s6_native_p2_only.py": "533dfa16395c041c610130f90d0489300fdd548f",
    "ci/guards/issue541_arch_s6_p2_independence_p0.py": "20543b4e90655f1bf3c75ca28babc7a12031722c",
}
FLOW_ACTIVE = (
    "FLOW_NATIVE_SOURCE_BOUND_P1_PASS",
    "FLOW_IDEAL_GAS_DIRECT_MATERIAL_NATIVE_P2_PASS",
    "FLOW_EI10_EI16_FOUR_FIXTURE_NATIVE_P2_PASS",
    "FLOW_DBASE_LEGACY_P2_RETIRED_NEWONLY_P05_OWNS_417_941",
)
P6 = {"p6_newonly_s6_build", "p6_newonly_s6_native_p2",
      "p6_public_d_100row_native_p2"}
RETIRED_ARCH = "issue541_arch_s6_hybrid_native_p2"


def need(value, code):
    if not value:
        raise ValueError("ISSUE816_FLOW_ARCH_RETIRE_" + code)


def blob(raw):
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode() + b"\0" + raw
    ).hexdigest()


def validate(flow, native, p6, contract, frozen):
    for path, sha in ARCHIVED.items():
        need(path in frozen and blob(frozen[path]) == sha,
             "ARCHIVE_BLOB_MISMATCH_" + path)
    need("on:\n  pull_request:\n    branches: [main]" in flow and
         "\n  workflow_dispatch:" in flow, "FLOW_EVENT_GUARD")
    need(all(marker in flow for marker in FLOW_ACTIVE),
         "FLOW_EI_H_RETAINED_NATIVE_LOST")
    need("P2 - exact binary EI-H ideal-gas and direct existing material" in flow and
         "P2 - EI10 EI16 four-fixture Native reduction" in flow,
         "FLOW_RETAINED_NATIVE_STEPS_LOST")
    need("run_chemistry_s6_p2_only.py" not in flow and
         "FLOW_PINNED_DBASE_417_941_NATIVE_P2_PASS" not in flow and
         "flow_dbase_native_p2" not in flow,
         "FLOW_LEGACY_POSITIVE_REINTRODUCED")
    need("\njobs:\n" in native, "NATIVE_JOB_SECTION_MISSING")
    jobs = set(re.findall(r"(?m)^  ([a-z][a-z0-9_-]*):\s*$",
                          native.split("\njobs:\n", 1)[1]))
    p6_jobs = set(re.findall(r"(?m)^  ([a-z][a-z0-9_-]*):\s*$",
                             p6.split("\njobs:\n", 1)[1]))
    need(RETIRED_ARCH not in native and RETIRED_ARCH not in p6, "ARCH_HYBRID_POSITIVE_REINTRODUCED")
    need(P6 == p6_jobs and not (P6 & jobs) and
         {"issue541_arch_dd_native_p2", "issue402_core_four_native_p2"} <= jobs,
         "CURRENT_NATIVE_GATES_MISSING")
    need(all(marker in p6 for marker in (
        "P05_NEGATIVES", "P6_NEWONLY", "P6_PUBLIC")),
        "P6_PROTECTED_NATIVE_GATES_MISSING")
    owned = contract["workflow_owners"][NATIVE]["jobs"]
    need(len(owned) == 4 and set(owned) == jobs and
         set(contract["workflow_owners"][P6_MANUAL]["jobs"]) == p6_jobs,
         "NATIVE_MANUAL_JOB_SCOPE_MISMATCH")


def load():
    return (
        (ROOT / FLOW).read_text(encoding="utf-8"),
        (ROOT / NATIVE).read_text(encoding="utf-8"),
        (ROOT / P6_MANUAL).read_text(encoding="utf-8"),
        json.loads((ROOT / CONTRACT).read_text(encoding="utf-8")),
        {name: (ROOT / name).read_bytes() for name in ARCHIVED},
    )


def self_test():
    f, n, p, c, a = load()
    validate(f, n, p, c, a)
    mutants = [
        ("old_flow", f + "run_chemistry_s6_p2_only.py", n, p, c, a),
        ("old_marker", f + "FLOW_PINNED_DBASE_417_941_NATIVE_P2_PASS", n, p, c, a),
        ("lost_ei", f.replace(FLOW_ACTIVE[2], "LOST_EI", 1), n, p, c, a),
        ("old_arch_job", f, n + "\n  " + RETIRED_ARCH + ":\n", p, c, a),
        ("lost_arch_dd", f, n.replace("  issue541_arch_dd_native_p2:",
                    "  removed_arch_dd_native_p2:", 1), p, c, a),
        ("lost_p6", f, n, p.replace("  p6_newonly_s6_native_p2:",
                    "  removed_p6_newonly_s6_native_p2:", 1), c, a),
    ]
    bad_contract = copy.deepcopy(c)
    bad_contract["workflow_owners"][NATIVE]["jobs"].append(RETIRED_ARCH)
    mutants.append(("scope_reverted", f, n, p, bad_contract, a))
    for path in ARCHIVED:
        changed = dict(a)
        changed[path] += b"\n# mutated historical bytes"
        mutants.append(("archive_mutation_" + path, f, n, p, c, changed))
    for name, flow, native, p6, contract, frozen in mutants:
        try:
            validate(flow, native, p6, contract, frozen)
        except (ValueError, KeyError, IndexError):
            continue
        raise AssertionError("ISSUE816_UNREJECTED_MUTATION_" + name)
    print("ISSUE816_FLOW_ARCH_RETIREMENT_NEGATIVES_" + str(len(mutants)) + "_PASS")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    try:
        if args.self_test:
            self_test()
        if args.check or not args.self_test:
            validate(*load())
            print("ISSUE816_FLOW_ARCH_LEGACY_S6_RETIREMENT_P0_PASS")
        return 0
    except (ValueError, OSError, KeyError, AssertionError, IndexError) as exc:
        print("ISSUE816_FLOW_ARCH_P0_FAIL", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
