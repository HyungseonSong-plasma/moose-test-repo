"""P0: code5-A four-Factory manifest must fail closed and never authorize deletion."""
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "code5_retirement_manifest", ROOT / "ci/code5_retirement_manifest.py")
assert spec and spec.loader
code5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(code5)


def fixture_reports() -> dict:
    head = "a" * 40
    reports = {}
    for index, target in enumerate(code5.TARGETS):
        s = {
            "target": target,
            "repository_head": head,
            "graph_id": "structural-graph:" + str(index),
            "status": "INCOMPLETE",
            "edges": [{"evidence": {"path": code5.SHARED_H, "blob_sha": "c" * 40}}],
        }
        f = {
            "target": target,
            "graph_id": "functional-graph:" + str(index),
            "status": "FUNCTIONAL_SOURCE_RECORDED_WITH_OPEN_OBLIGATIONS",
            "source_identity": {
                "repository_head": head,
                "source_blobs": {code5.SHARED_C: "b" * 40},
            },
        }
        t = {
            "target": target,
            "source_identity": {
                "repository_head": head,
                "structural_graph_id": s["graph_id"],
                "functional_graph_id": f["graph_id"],
            },
            "graph_id": "transition-graph:" + str(index),
            "plan_status": "CONDITIONAL_PLAN",
            "execution_status": "NOT_EXECUTED",
            "safe_delete": "HOLD",
            "shared_owner_contract": {
                "source_path": code5.SHARED_C,
                "co_registered_classes": list(code5.TARGETS),
            },
            "candidate_rewiring_options": [],
            "consumer_dispositions": [{
                "consumer_id": "consumer:" + str(index),
                "structural_edge_id": "edge:" + str(index),
                "instance_id": "instance:" + str(index),
                "role": "DECLARED_INPUT_NOT_RUNTIME",
                "input_path": "tests/maintained_case.i",
                "block_path": "FVKernels/k",
                "reference_scope": "CURRENT_SOURCE_NOT_PROVEN_ACTIVE",
                "disposition": "HOLD_UNKNOWN",
                "before": {"runtime_activation": "NOT_OBSERVED"},
                "after_proposal": {"candidate_options": []},
                "functional_claim_ids": ["time_law"],
            }],
            "blocking_obligations": [{
                "obligation_id": "obligation:" + str(index),
                "kind": "REPLACEMENT_PARITY_NOT_PROVEN",
                "consumer": None,
                "required_evidence": "independent test",
                "gate": "P1_P2_P3",
                "oracle": "INDEPENDENT",
                "owner": "DOMAIN_OWNER",
                "status": "OPEN",
                "origin_ref": "source",
            }],
            "steps": [{"eligible_to_execute": False}],
            "change_sites": {
                "declared_input_and_other_consumer_paths": ["tests/maintained_case.i"],
                "generator_paths": ["scripts/generate.py"],
                "generated_output_candidates_not_observed": ["tmp/generated.i"],
                "workflow_paths": [".github/workflows/ci.yml"],
            },
        }
        reports[target] = (s, f, t)
    return reports


class Code5ManifestPureP0(unittest.TestCase):
    def test_no_historical_or_lexical_auto_rewire(self):
        c = {"role": "DECLARED_INPUT_NOT_RUNTIME", "instance_id": "i",
             "disposition": "HOLD_UNKNOWN"}
        c["input_path"] = "experiments/Issue3_dielectric_surface_charge/d6_2d_integrated.i"
        self.assertEqual(code5.disposition(c), "CANONICAL_OR_HISTORICAL_ROLE_REVIEW_NO_EDIT")
        c["input_path"] = "experiments/Issue402_plasma_dsl_g1/native/s6_c0_physics_base_no_d1.i"
        self.assertEqual(code5.disposition(c), "CANONICAL_OR_HISTORICAL_ROLE_REVIEW_NO_EDIT")
        c["input_path"] = "tests/maintained_case.i"
        c["role"] = "LEXICAL_MENTION_NOT_CONSUMER"
        self.assertEqual(code5.disposition(c), "REFERENCE_ONLY_NO_EDIT")
        c["role"] = "DECLARED_INPUT_NOT_RUNTIME"
        self.assertEqual(code5.disposition(c), "REWIRE_CANDIDATE_UNVERIFIED")
        c["disposition"] = "PRESERVE_HISTORICAL"
        self.assertEqual(code5.disposition(c), "PRESERVE_HISTORICAL_NO_EDIT")

    def test_four_targets_aggregate_without_delete(self):
        m = code5.build_manifest("a" * 40, fixture_reports())
        self.assertEqual(len(m["targets"]), 4)
        self.assertEqual(len(m["consumers"]), 4)
        self.assertEqual(len(m["blocking_obligations"]), 4)
        self.assertEqual(m["safe_delete"], "HOLD")
        self.assertEqual(m["all_four_owner_gates"], "BLOCKED")
        self.assertEqual(m["transition_execution"], "NOT_EXECUTED")
        self.assertEqual(m["caller_zero"], "NOT_PROVEN")
        self.assertEqual(
            m["change_sites"]["rewire_candidates_NOT_APPROVED"],
            ["tests/maintained_case.i"])
        self.assertEqual(m["source_blob_sha"], "b" * 40)
        self.assertEqual(m["header_blob_sha"], "c" * 40)
        self.assertEqual(
            m["manifest_id"], code5.structural.stable_id(
                "code5-manifest", {k: v for k, v in m.items() if k != "manifest_id"}))
        self.assertEqual(m, code5.build_manifest("a" * 40, fixture_reports()))

    def test_missing_owner_or_false_delete_rejected(self):
        records = fixture_reports()
        records.pop(code5.TARGETS[-1])
        with self.assertRaisesRegex(ValueError, "CODE5_MISSING_OR_EXTRA"):
            code5.build_manifest("a" * 40, records)
        records = fixture_reports()
        x = copy.deepcopy(records[code5.TARGETS[0]][2])
        x["shared_owner_contract"]["co_registered_classes"].pop()
        records[code5.TARGETS[0]] = (*records[code5.TARGETS[0]][:2], x)
        with self.assertRaisesRegex(ValueError, "CODE5_OWNER_OR_SAFETY"):
            code5.build_manifest("a" * 40, records)
        records = fixture_reports()
        x = copy.deepcopy(records[code5.TARGETS[0]][2])
        x["safe_delete"] = "PASS"
        records[code5.TARGETS[0]] = (*records[code5.TARGETS[0]][:2], x)
        with self.assertRaisesRegex(ValueError, "CODE5_OWNER_OR_SAFETY"):
            code5.build_manifest("a" * 40, records)

    def test_inconsistent_source_or_graph_rejected(self):
        records = fixture_reports()
        f = copy.deepcopy(records[code5.TARGETS[1]][1])
        f["source_identity"]["source_blobs"][code5.SHARED_C] = "c" * 40
        records[code5.TARGETS[1]] = (records[code5.TARGETS[1]][0], f, records[code5.TARGETS[1]][2])
        with self.assertRaisesRegex(ValueError, "CODE5_SHARED_SOURCE_BLOB_DIVERGED"):
            code5.build_manifest("a" * 40, records)
        records = fixture_reports()
        s = copy.deepcopy(records[code5.TARGETS[2]][0])
        s["edges"][0]["evidence"]["blob_sha"] = "d" * 40
        records[code5.TARGETS[2]] = (s, *records[code5.TARGETS[2]][1:])
        with self.assertRaisesRegex(ValueError, "CODE5_SHARED_HEADER_BLOB_DIVERGED"):
            code5.build_manifest("a" * 40, records)
        records = fixture_reports()
        t = copy.deepcopy(records[code5.TARGETS[2]][2])
        t["source_identity"]["functional_graph_id"] = "forged"
        records[code5.TARGETS[2]] = (*records[code5.TARGETS[2]][:2], t)
        with self.assertRaisesRegex(ValueError, "CODE5_CROSS_GRAPH"):
            code5.build_manifest("a" * 40, records)


class Code5ManifestLiveP0(unittest.TestCase):
    def test_generate_four_triples_from_exact_head_without_mutation(self):
        # All reported steps remain unexecuted. A clean tracked checkout is
        # required; no source code or GitHub state is changed by generation.
        head = code5.structural.git(ROOT, "rev-parse", "HEAD")
        with tempfile.TemporaryDirectory(prefix="code5-fdeg-") as directory:
            folder = Path(directory)
            manifest = code5.produce(ROOT, head, folder)
            self.assertEqual(manifest["safe_delete"], "HOLD")
            self.assertEqual(len(manifest["targets"]), 4)
            self.assertEqual(
                len(list(folder.glob("*.json"))), 13)
            saved = json.loads(
                (folder / "code5-retirement-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["manifest_id"], manifest["manifest_id"])
            self.assertFalse(any(
                x["owner_gate"] != "NOT_DISCHARGED" for x in manifest["targets"]))


if __name__ == "__main__":
    unittest.main()
