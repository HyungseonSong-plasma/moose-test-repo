#!/usr/bin/env python3
"""code6 read-only exact-HEAD Structural/Functional/Transition baseline receipt.

The census checks *declared Python input templates*. It never certifies generated
input execution, effective Functor resolution, numeric parity or safe deletion.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci/guards"))
import fdeg_structural as structural  # noqa: E402
import fdeg_functional as functional  # noqa: E402
import fdeg_transition as transition  # noqa: E402

TARGET = "PhysicsFVMassFractionTimeDerivative"
CENSUS = Path("ci/baselines/code6_retirement_consumers.json")
TYPE = re.compile(r"^\s*type\s*=\s*PhysicsFVMassFractionTimeDerivative\s*(?:#.*)?$")
BLOCK = re.compile(r"^\s*\[\s*([A-Za-z_]\w*)\s*\]\s*$")
PARAM = re.compile(r"^\s*(variable|rho)\s*=\s*([A-Za-z_]\w*)\s*(?:#.*)?$")
END_BLOCK = re.compile(r"^\s*\[\s*(?:\.\.?/?)?\s*\]\s*$")


def parse_declared_instances(text: str) -> list[dict]:
    """Extract immediate type/variable/rho from source templates, not runtime .i."""
    lines = text.splitlines()
    instances = []
    for i, line in enumerate(lines):
        if not TYPE.fullmatch(line):
            continue
        before = []
        for j in range(i - 1, max(-1, i - 7), -1):
            match = BLOCK.fullmatch(lines[j])
            if match:
                before.append(match.group(1))
                break
        if not before:
            raise ValueError(f"CODE6_DECLARATION_WITHOUT_BLOCK:line={i + 1}")
        bindings = {}
        for raw in lines[i + 1:i + 8]:
            if END_BLOCK.fullmatch(raw) or BLOCK.fullmatch(raw):
                break
            match = PARAM.fullmatch(raw)
            if match:
                bindings[match.group(1)] = match.group(2)
        if not {"variable", "rho"} <= bindings.keys():
            raise ValueError(f"CODE6_DECLARATION_MISSING_BINDING:line={i + 1}")
        instances.append({"block": before[0], "variable": bindings["variable"],
                          "rho": bindings["rho"], "type_line": i + 1})
    return instances


def check_census(root: Path, census: dict) -> list[dict]:
    if census.get("schema") != "code6.consumer_census.v0.1" or census.get("target") != TARGET:
        raise ValueError("CODE6_CENSUS_SCHEMA_OR_TARGET")
    declared = census.get("consumers", [])
    if len(declared) != census.get("expected_direct_script_count") or len(declared) != 10:
        raise ValueError("CODE6_SCRIPT_COUNT_DRIFT")
    records = []
    for entry in declared:
        path = entry["path"]
        source_path = functional.safe_path(root, path)
        raw = source_path.read_bytes()
        actual = parse_declared_instances(raw.decode("utf-8"))
        expected = [{key: item[key] for key in ("block", "variable", "rho")}
                    for item in entry["instances"]]
        observed = [{key: item[key] for key in ("block", "variable", "rho")}
                    for item in actual]
        if actual and observed != expected:
            raise ValueError("CODE6_CONSUMER_DECLARATION_DRIFT:" + path)
        if not actual or observed != expected:
            raise ValueError("CODE6_CONSUMER_DECLARATION_MISSING:" + path)
        records.append({"path": path, "blob_sha": structural.blob_sha(raw),
                        "status": "DECLARED_TEMPLATE_NOT_RUNTIME",
                        "instances": actual})
    if sum(len(record["instances"]) for record in records) != census.get(
            "expected_declared_instance_count") or sum(
            len(record["instances"]) for record in records) != 15:
        raise ValueError("CODE6_INSTANCE_COUNT_DRIFT")
    return records


def self_test() -> None:
    good = """[FVKernels]
  [w_O_time]
    type = PhysicsFVMassFractionTimeDerivative
    variable = w_O
    rho = rho_const
  []
[]
"""
    one = parse_declared_instances(good)
    assert [(x["block"], x["variable"], x["rho"]) for x in one] == [
        ("w_O_time", "w_O", "rho_const")]
    compact = "[wt]\n type=PhysicsFVMassFractionTimeDerivative\n variable=w_Om\n rho=rho_const\n []\n"
    assert parse_declared_instances(compact)[0]["block"] == "wt"
    assert parse_declared_instances("assert 'PhysicsFVMassFractionTimeDerivative' not in output") == []
    try:
        parse_declared_instances(good.replace("rho = rho_const", "density = other"))
    except ValueError as exc:
        assert "MISSING_BINDING" in str(exc)
    else:
        raise AssertionError("CODE6_NEGATIVE_MISSING_RHO_NOT_REJECTED")
    print("CODE6_CENSUS_SELF_TEST=PASS")


def run(root: Path, expected_head: str) -> tuple[dict, dict, dict, dict]:
    actual_head = structural.git(root, "rev-parse", "HEAD")
    if actual_head != expected_head:
        raise ValueError("CODE6_EXACT_HEAD_MISMATCH")
    census_raw = (root / CENSUS).read_bytes()
    census = json.loads(census_raw)
    records = check_census(root, census)
    # The Structural implementation verifies exact HEAD and a clean tracked
    # checkout; the Functional and Transition assemblers independently verify
    # graph identity and pinned C++/candidate witnesses.
    s = structural.scan(root, TARGET, expected_head)
    f = functional.assemble(root, s, TARGET, functional.load_registry(root),
                            expected_head)
    policy, policy_blob = transition.load_policy(root)
    t = transition.assemble(root, s, f, TARGET, policy, policy_blob, expected_head)
    if (t["safe_delete"] != "HOLD" or t["execution_status"] != "NOT_EXECUTED"
            or f["equivalence_verdict"] != "NOT_PROVEN"):
        raise ValueError("CODE6_UNSAFE_STATUS_PROMOTION")
    # These are known source paths, not certified complete consumer coverage.
    graph_paths = {e["evidence"]["path"] for e in s["edges"]
                   if e.get("evidence", {}).get("path")}
    absent = [c["path"] for c in records if c["path"] not in graph_paths]
    if absent:
        raise ValueError("CODE6_CENSUS_GRAPH_MISSING_SOURCE:" + ",".join(absent))
    receipt = {
        "schema": "code6.retirement_baseline.v0.1",
        "target": TARGET,
        "source_head": actual_head,
        "consumer_census_blob_sha": structural.blob_sha(census_raw),
        "census_scope": "TEN_SOURCE_DECLARED_PYTHON_TEMPLATES_NOT_GLOBAL_CALLER_ZERO",
        "census": records,
        "declared_script_count": len(records),
        "declared_instance_count": sum(len(c["instances"]) for c in records),
        "graph_ids": {"structural": s["graph_id"],
                      "functional": f["graph_id"],
                      "transition": t["graph_id"]},
        "schemas": {"structural": s["schema"], "functional": f["schema"],
                    "transition": t["schema"]},
        "structural_status": s["status"],
        "target_scoped_unresolved": s["target_scoped_unresolved"],
        "transition_blockers": [
            {"obligation_id": b["obligation_id"], "kind": b["kind"],
             "gate": b["gate"], "status": b["status"]}
            for b in t["blocking_obligations"]],
        "runtime": "NOT_OBSERVED",
        "numerical_equivalence": "NOT_PROVEN",
        "external_caller_zero": "NOT_PROVEN",
        "graph_only_planner_evaluation": "NOT_EVALUATED",
        "safe_delete": "HOLD",
        "next_action": "P1_PIN_EFFECTIVE_TIME_SCHEME_AND_RUN_CONTROLLED_NATIVE_A_B",
    }
    return s, f, t, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--expected-head")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            if not args.expected_head:
                return 0
        if not args.expected_head or not args.output_dir:
            parser.error("--expected-head and --output-dir are required for evidence generation")
        root = args.root.resolve()
        s, f, t, receipt = run(root, args.expected_head)
        dest = args.output_dir.resolve()
        dest.mkdir(parents=True, exist_ok=True)
        for name, report in (("structural", s), ("functional", f), ("transition", t),
                             ("baseline-receipt", receipt)):
            (dest / ("code6-" + name + ".json")).write_text(
                json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        print("CODE6_BASELINE_P0=PASS")
        print("CODE6_EVIDENCE_HEAD=" + receipt["source_head"])
        print("CODE6_SCRIPTS=10;DECLARED_KERNEL_INSTANCES=15")
        print("CODE6_RETIREMENT=HOLD")
        return 0
    except (ValueError, OSError, KeyError, TypeError, AssertionError) as exc:
        print("CODE6_BASELINE_P0=FAIL:" + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
