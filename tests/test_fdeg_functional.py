"""FDEG Functional v0.1 P0: source identity, graph join, and semantic negatives."""
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "fdeg_functional", ROOT / "ci/guards/fdeg_functional.py")
assert spec and spec.loader
functional = importlib.util.module_from_spec(spec)
spec.loader.exec_module(functional)
structural = functional.structural


class FunctionalP0Test(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.put("src/Legacy.C",
            'registerMooseObject("PhysicsApp", Legacy);\n'
            'auto params = FVElementalKernel::validParams();\n'
            'return -source / scale;\n')
        self.put("cases/electron.i",
            "[Kernels]\n  [./electron]\n    type = Legacy\n"
            "    variable = n_e\n    state_form = normalized\n"
            "    scale = 3.0\n  [../]\n[]\n")
        self.profile = {
            "target": "Legacy",
            "source": {"path": "src/Legacy.C",
                       "blob_sha": structural.blob_sha(self.source.read_bytes())},
            "capability": "SIGNED_SOURCE", "equation": "electron_continuity",
            "operator_kind": "FVElementalKernel", "notes": "signed source; not runtime",
            "claims": [{
                "id": "residual", "relation": "IMPLEMENTS",
                "to": "capability:SIGNED_SOURCE", "expression": "R=-source/scale",
                "anchors": ["return -source / scale;"], "mode": "normalized",
                "units": "source/scale", "conditions": ["scale>0"],
                "counterexamples": ["source sign flip"], "assumptions": [],
                "evidence_kind": "SOURCE_OBSERVATION"}],
            "alternatives": [{
                "candidate_type": "FVCoupledForce", "status": "CANDIDATE_UNVERIFIED",
                "conditions": ["same functor"], "semantic_risks": ["AD mismatch"],
                "requires": "INDEPENDENT_PARITY_PROOF"}],
            "required_discriminators": ["SIGN_FLIP", "SCALING", "AD_JACOBIAN"],
            "unresolved_semantics": ["RUNTIME_NOT_OBSERVED"],
            "historical_guards": ["NO_HISTORICAL_PARITY_PROMOTION"]}
        self.registry = {"schema": "fdeg.functional_registry.v0.1",
                         "profiles": {"Legacy": self.profile}}
        self.graph = structural.scan(self.root, "Legacy")

    def put(self, name, body):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        return p

    def assemble(self, graph=None, registry=None):
        return functional.assemble(self.root, graph or self.graph,
                                   "Legacy", registry or self.registry)

    def test_verified_claim_and_declared_instance_join(self):
        result = self.assemble()
        self.assertEqual(result["schema"], "fdeg.functional.v0.1")
        self.assertEqual(result["source_identity"]["structural_graph_id"],
                         self.graph["graph_id"])
        claims = [e for e in result["edges"] if e["relation"] == "IMPLEMENTS"]
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["claim_status"], "SOURCE_SUPPORTED")
        self.assertEqual(claims[0]["runtime_status"], "NOT_OBSERVED")
        self.assertEqual(claims[0]["witnesses"][0]["blob_sha"],
                         self.profile["source"]["blob_sha"])
        self.assertTrue(claims[0]["structural_registration_edge_ids"])
        consumers = [c for c in result["consumer_contracts"] if c["instance_id"]]
        self.assertEqual(len(consumers), 1)
        self.assertEqual(consumers[0]["role"], "DECLARED_INPUT_NOT_RUNTIME")
        bound = {b["name"]: b["raw_value"] for b in consumers[0]["declared_bindings"]}
        self.assertEqual(bound["state_form"], "normalized")
        self.assertEqual(bound["variable"], "n_e")
        self.assertEqual(consumers[0]["effective_runtime_binding"], "NOT_OBSERVED")
        self.assertEqual(result["equivalence_verdict"], "NOT_PROVEN")

    def test_stability_and_candidate_must_stay_unverified(self):
        a, b = self.assemble(), self.assemble()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(a["graph_id"], b["graph_id"])
        candidate = next(e for e in a["edges"] if e["relation"] == "ALTERNATIVE_CANDIDATE")
        self.assertEqual(candidate["claim_status"], "CANDIDATE_UNVERIFIED")
        self.assertFalse(candidate["witnesses"])
        self.assertIn("NO_CALLER_ZERO", a["safety"])

    def test_sign_mutation_rejects_stale_source_blob(self):
        self.source.write_text(self.source.read_text().replace("-source", "source"),
                               encoding="utf-8")
        fresh = structural.scan(self.root, "Legacy")
        with self.assertRaisesRegex(ValueError, "STALE_FUNCTIONAL_PROFILE_SOURCE_BLOB"):
            self.assemble(graph=fresh)

    def test_missing_source_anchor_rejected(self):
        altered = copy.deepcopy(self.registry)
        altered["profiles"]["Legacy"]["claims"][0]["anchors"] = ["return source / scale;"]
        with self.assertRaisesRegex(ValueError, "FUNCTIONAL_SOURCE_ANCHOR_MISSING"):
            self.assemble(registry=altered)

    def test_forged_graph_and_edge_ids_rejected(self):
        tampered = copy.deepcopy(self.graph)
        tampered["edges"][0]["relation"] = "FORGED_RUNTIME_EVIDENCE"
        with self.assertRaisesRegex(ValueError, "STRUCTURAL_GRAPH_ID_MISMATCH"):
            self.assemble(graph=tampered)
        tampered["graph_id"] = structural.stable_id(
            "graph", {k: v for k, v in tampered.items() if k != "graph_id"})
        with self.assertRaisesRegex(ValueError, "STRUCTURAL_EDGE_ID_MISMATCH"):
            self.assemble(graph=tampered)

    def test_mutated_input_without_rebuild_is_rejected(self):
        self.put("cases/electron.i",
                 "[Kernels]\n  [./electron]\n    type = Legacy\n"
                 "    state_form = physical\n  [../]\n[]\n")
        with self.assertRaisesRegex(ValueError, "STRUCTURAL_WITNESS_MISMATCH"):
            self.assemble()

    def test_legacy_schema_target_and_wrong_head_rejected(self):
        tampered = copy.deepcopy(self.graph)
        tampered["schema"] = "fdeg.structural.v0.1"
        with self.assertRaisesRegex(ValueError, "STRUCTURAL_SCHEMA_OR_TARGET_MISMATCH"):
            self.assemble(graph=tampered)
        with self.assertRaisesRegex(ValueError, "STRUCTURAL_EXACT_HEAD_MISMATCH"):
            functional.assemble(self.root, self.graph, "Legacy",
                                self.registry, "a" * 40)

    def test_no_registry_equivalence_promotion(self):
        tampered = copy.deepcopy(self.registry)
        tampered["profiles"]["Legacy"]["alternatives"][0]["status"] = "NUMERICALLY_VALIDATED"
        with self.assertRaisesRegex(ValueError, "FUNCTIONAL_ALTERNATIVE_CANNOT_ASSERT_EQUIVALENCE"):
            self.assemble(registry=tampered)

    def test_incomplete_structural_scan_is_not_caller_zero(self):
        self.put("cases/unknown.i", "type = $dynamic_type\n")
        result = self.assemble(graph=structural.scan(self.root, "Legacy"))
        self.assertIn("STRUCTURAL_SCAN_INCOMPLETE", result["unresolved_obligations"])
        self.assertEqual(result["equivalence_verdict"], "NOT_PROVEN")
        self.assertEqual(result["safety"],
                         "NO_CALLER_ZERO_TRANSITION_OR_RETIREMENT_AUTHORIZATION")


class LiveContractsP0Test(unittest.TestCase):
    def test_six_source_pinned_profiles_and_anchors(self):
        registry = functional.load_registry(ROOT)
        self.assertEqual(len(registry["profiles"]), 6)
        for target, profile in sorted(registry["profiles"].items()):
            with self.subTest(target=target):
                functional.validate_registry_profile(profile)
                witnesses, blobs = functional.source_witnesses(ROOT, profile)
                self.assertTrue(witnesses)
                self.assertIn(profile["source"]["path"], blobs)
                self.assertTrue(all(w["line_start"] >= 1 for w in witnesses))
                self.assertTrue(profile["required_discriminators"])
                self.assertTrue(profile["unresolved_semantics"])

    def test_real_source_signed_projection_graph_join(self):
        target = "PhysicsFVElectronReactionSource"
        graph = structural.scan(ROOT, target)
        result = functional.assemble(ROOT, graph, target,
                                     functional.load_registry(ROOT))
        self.assertEqual(result["capability"],
                         "SIGNED_ELECTRON_NUMBER_SOURCE_PROJECTION")
        self.assertTrue(any(e["relation"] == "IMPLEMENTS" and
                            "normalized" in e["expression"] for e in result["edges"]))
        self.assertEqual(result["equivalence_verdict"], "NOT_PROVEN")
        self.assertTrue(result["unresolved_obligations"])


if __name__ == "__main__":
    unittest.main()
