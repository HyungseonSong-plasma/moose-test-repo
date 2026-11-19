"""FDEG Transition v0.1 P0: graph identity, consumer dispositions, DAG, HOLD."""
from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "fdeg_transition", ROOT / "ci/guards/fdeg_transition.py")
assert spec and spec.loader
transition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transition)
structural = transition.structural
functional = transition.functional


class PureTransitionGraphP0Test(unittest.TestCase):
    """Isolated graph-only composition: no source access, no runtime, no physics."""
    def setUp(self):
        self.policy, self.policy_sha = transition.load_policy(ROOT)
        self.target = "PhysicsFVMassFractionTimeDerivative"
        self.s = {
            "schema": "fdeg.structural.v0.3", "target": self.target,
            "repository_head": "a" * 40,
            "graph_id": "graph:fixture", "status": "INCOMPLETE",
            "target_scoped_unresolved": [{
                "path": "scripts/generate.py", "line": 12,
                "reason": "GENERATED_INPUT_NOT_TRACKED_OR_OBSERVED"}],
            "scan_errors": [],
            "edges": [
                {"edge_id": "edge:declaration", "from": "instance:one",
                 "to": "class:" + self.target, "relation": "INPUT_INSTANTIATES",
                 "revision_scope": "CURRENT_SOURCE_NOT_PROVEN_ACTIVE"},
                {"edge_id": "edge:history", "from": "file:history.i",
                 "to": "class:" + self.target, "relation": "MENTIONS_SYMBOL",
                 "revision_scope": "HISTORICAL_SOURCE_NOT_PROVEN_ACTIVE"},
            ],
            "instances": [{"instance_id": "instance:one"}],
        }
        self.f = {
            "schema": "fdeg.functional.v0.2", "target": self.target,
            "graph_id": "functional-graph:fixture",
            "source_identity": {
                "repository_head": self.s["repository_head"],
                "structural_graph_id": self.s["graph_id"]},
            "runtime_observation": "NOT_OBSERVED",
            "equivalence_verdict": "NOT_PROVEN",
            "replacement_verdict": "ALL_CANDIDATES_UNVERIFIED",
            "discriminator_contracts": {
                "VARIABLE_DENSITY_COUNTEREXAMPLE": {
                    "status": "NOT_EVALUATED", "observable": "time residual",
                    "expected": "difference for rho_n != rho_old"}},
            "unresolved_obligations": ["PER_CONSUMER_STATE_REPRESENTATION"],
            "semantic_replacement_diffs": [{
                "candidate_type": "PhysicsFVConservativeMassFractionTimeDerivative",
                "functional_edge_id": "functional-edge:candidate",
                "comparison_contract": {"decision": "HOLD",
                    "dimensions": {"residual_formula": {
                        "candidate_expected": "(rho_n-rho_old)*w_old/dt",
                        "parity_status": "NOT_EVALUATED"}}},
                "candidate_source_witnesses": [],
                "transition_permission": "HOLD",
                "equivalence_verdict": "NOT_PROVEN"
            }],
            "edges": [
                {"claim_id": "claim:" + self.target + ":time_term",
                 "edge_id": "functional-edge:time"},
                {"claim_id": "candidate:" + self.target +
                 ":PhysicsFVConservativeMassFractionTimeDerivative",
                 "edge_id": "functional-edge:candidate"}],
            "preservation_contract": {"claim_ids": ["time_term"]},
            "consumer_contracts": [
                {"structural_edge_id": "edge:declaration",
                 "source_node": "instance:one", "role": "DECLARED_INPUT_NOT_RUNTIME",
                 "evidence_strength": "SOURCE_ONLY",
                 "instance_id": "instance:one", "input_path": "tests/current.i",
                 "block_path": "FVKernels/time", "declared_bindings": [
                     {"name": "rho", "raw_value": "rho_const", "line": 15},
                     {"name": "variable", "raw_value": "w_O2p", "line": 16}],
                 "declared_mode": "NOT_EXPLICITLY_SET",
                 "functional_effect_if_removed": "rho * _u_dot"},
                {"structural_edge_id": "edge:history",
                 "source_node": "file:history.i", "role": "LEXICAL_MENTION_NOT_CONSUMER",
                 "evidence_strength": "LEXICAL_MENTION",
                 "instance_id": None, "input_path": "history.i",
                 "block_path": None, "declared_bindings": [],
                 "declared_mode": "UNKNOWN",
                 "functional_effect_if_removed": None}
            ],
            "generator_consumer_routes": [
                {"source": "scripts/generate.py", "activation": "NOT_OBSERVED",
                 "output_candidates": ["generated/target.i"]}],
            "workflow_execution_routes": [{"workflow_path": ".github/workflows/ci.yml"}],
            "build_and_header_ownership": {
                "translation_units": [{"source_path": "src/MassFraction.C"}]},
            "shared_translation_unit": None,
        }

    def compose(self, s=None, f=None, policy=None):
        return transition.compose(s or self.s, f or self.f,
                                  policy or self.policy, self.policy_sha)

    def test_graph_only_exposes_consumer_disposition_and_blocking_obligations(self):
        report = self.compose()
        self.assertEqual(report["schema"], "fdeg.transition.v0.1")
        self.assertEqual(report["plan_status"], "CONDITIONAL_PLAN")
        self.assertEqual(report["safe_delete"], "HOLD")
        self.assertEqual(report["caller_zero"], "NOT_PROVEN")
        self.assertEqual(report["execution_status"], "NOT_EXECUTED")
        current = next(c for c in report["consumer_dispositions"] if c["instance_id"])
        self.assertEqual(current["disposition"], "HOLD_UNKNOWN")
        self.assertEqual(current["before"]["bindings"][0]["raw_value"], "rho_const")
        self.assertEqual(current["before"]["runtime_activation"], "NOT_OBSERVED")
        self.assertIn("REWIRE_CANDIDATE", current["disposition_proposal"])
        self.assertTrue(current["blocking_obligation_ids"])
        self.assertTrue(any("rho_n" in str(x) for x in report["candidate_rewiring_options"]))
        self.assertIn("generated/target.i",
                      report["change_sites"]["generated_output_candidates_not_observed"])

    def test_ordered_dag_and_rollback_pinned_to_exact_head(self):
        result = self.compose()
        steps = result["steps"]
        core_steps = [step for step in steps
                      if step["operation"] in transition.STEP_ORDER]
        self.assertEqual(len(core_steps), len(transition.STEP_ORDER))
        self.assertEqual(len(steps), len(transition.STEP_ORDER) + 2)
        for i, step in enumerate(core_steps):
            self.assertEqual(step["status"], "PLANNED")
            self.assertEqual(step["execution_status"], "NOT_EXECUTED")
            self.assertFalse(step["eligible_to_execute"])
            self.assertEqual(step["rollback"]["baseline_head"], "a" * 40)
            expected = ["step:" + transition.STEP_ORDER[i - 1]] if i else []
            if step["operation"] == "REWIRE_DECLARED_CONSUMERS":
                expected = ["step:REWIRE_CONSUMER_CANDIDATE:edge:declaration"]
            if step["operation"] == "VERIFY_FUNCTION_AND_HISTORY":
                expected.append("step:PRESERVE_HISTORICAL_CONSUMER:edge:history")
            self.assertEqual(step["depends_on_steps"], expected)
            self.assertTrue(all(x["status"] == "NOT_EVALUATED"
                                for x in step["verification_gates"]))
        rewire = next(s for s in steps if s["operation"] == "REWIRE_DECLARED_CONSUMERS")
        self.assertEqual(rewire["expected_graph_delta"]["may_remove_structural_edge_ids"],
                         ["edge:declaration"])
        self.assertFalse(rewire["expected_graph_delta"]["observed_removed_edges"])
        self.assertTrue(any(e["relation"] == "ROLLBACK_TO" for e in result["edges"]))
        self.assertTrue(any(e["relation"] == "DEPENDS_ON_STEP" for e in result["edges"]))

    def test_per_consumer_rewire_step_has_exact_edge_and_rollback(self):
        report = self.compose()
        step = next(s for s in report["steps"]
                    if s["operation"] == "REWIRE_CONSUMER_CANDIDATE")
        self.assertEqual(step["structural_edge_id"], "edge:declaration")
        self.assertEqual(step["instance_id"], "instance:one")
        self.assertEqual(step["affected_paths"], ["tests/current.i"])
        self.assertEqual(step["after_proposal"]["binding_status"],
                         "NOT_SPECIFIED_UNTIL_REPLACEMENT_PROOF")
        self.assertEqual(step["expected_graph_delta"]["may_remove_structural_edge_ids"],
                         ["edge:declaration"])
        self.assertFalse(step["eligible_to_execute"])
        self.assertEqual(step["rollback"]["baseline_head"], "a" * 40)
        self.assertTrue(any(e["relation"] == "REWIRE_STEP"
                            and e["from"] == step["step_id"] for e in report["edges"]))

    def test_historical_step_is_no_modification_and_separate_replay(self):
        report = self.compose()
        step = next(s for s in report["steps"]
                    if s["operation"] == "PRESERVE_HISTORICAL_CONSUMER")
        self.assertEqual(step["affected_paths"], [])
        self.assertEqual(step["expected_graph_delta"]["may_remove_structural_edge_ids"], [])
        gates = {item["gate"] for item in step["verification_gates"]}
        self.assertIn("PINNED_HISTORICAL_REPLAY_SEPARATE", gates)
        self.assertIn("CURRENT_BINARY_COMPATIBILITY_INDEPENDENT", gates)
        self.assertFalse(step["eligible_to_execute"])

    def test_historical_lexical_not_promoted_to_active_consumer(self):
        result = self.compose()
        old = next(c for c in result["consumer_dispositions"] if c["source_node"] == "file:history.i")
        self.assertEqual(old["disposition"], "PRESERVE_HISTORICAL")
        self.assertEqual(old["disposition_proposal"], "PRESERVE_HISTORY")
        self.assertIsNone(old["after_proposal"]["expected_removed_structural_edge_id"])
        self.assertEqual(old["function_to_preserve_if_active"], None)
        self.assertEqual(old["functional_claim_ids"], [])

    def test_determinism_including_edge_hashes(self):
        a, b = self.compose(), self.compose()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(a["graph_id"], b["graph_id"])
        self.assertEqual(
            a["graph_id"],
            structural.stable_id("transition-graph",
                                 {k: v for k, v in a.items() if k != "graph_id"}))
        self.assertEqual(len({e["edge_id"] for e in a["edges"]}), len(a["edges"]))

    def test_no_consumers_is_not_caller_zero(self):
        f = copy.deepcopy(self.f)
        f["consumer_contracts"] = []
        result = self.compose(f=f)
        self.assertEqual(result["caller_zero"], "NOT_PROVEN")
        self.assertTrue(any(b["kind"] == "NO_IDENTIFIED_CONSUMERS_IS_NOT_CALLER_ZERO"
                            for b in result["blocking_obligations"]))

    def test_bad_candidate_promotion_is_rejected(self):
        f = copy.deepcopy(self.f)
        f["semantic_replacement_diffs"][0]["transition_permission"] = "PASS"
        with self.assertRaisesRegex(ValueError, "TRANSITION_CANDIDATE_FALSE_PROMOTION"):
            self.compose(f=f)
        f = copy.deepcopy(self.f)
        f["semantic_replacement_diffs"][0]["comparison_contract"]["decision"] = "APPROVED"
        with self.assertRaisesRegex(ValueError, "TRANSITION_CANDIDATE_FALSE_PROMOTION"):
            self.compose(f=f)

    def test_bad_runtime_and_discriminator_pass_rejected(self):
        f = copy.deepcopy(self.f)
        f["runtime_observation"] = "PASS"
        with self.assertRaisesRegex(ValueError, "TRANSITION_INVALID_FUNCTIONAL_VERDICT"):
            self.compose(f=f)
        f = copy.deepcopy(self.f)
        f["discriminator_contracts"]["VARIABLE_DENSITY_COUNTEREXAMPLE"]["status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "TRANSITION_DISCRIMINATOR_FALSE_PASS"):
            self.compose(f=f)

    def test_missing_instance_or_edge_rejected(self):
        s = copy.deepcopy(self.s)
        s["instances"] = []
        with self.assertRaisesRegex(ValueError, "TRANSITION_CONSUMER_INSTANCE_NOT_IN_STRUCTURAL"):
            self.compose(s=s)
        s = copy.deepcopy(self.s)
        s["edges"].pop(0)
        with self.assertRaisesRegex(ValueError, "TRANSITION_CONSUMER_EDGE_NOT_IN_STRUCTURAL"):
            self.compose(s=s)

    def test_dynamic_generator_cannot_assert_runtime_activation(self):
        f = copy.deepcopy(self.f)
        f["generator_consumer_routes"][0]["activation"] = "EXECUTED"
        with self.assertRaisesRegex(ValueError, "TRANSITION_GENERATOR_FALSE_ACTIVATION"):
            self.compose(f=f)

    def test_forged_cross_graph_id_rejected(self):
        f = copy.deepcopy(self.f)
        f["source_identity"]["structural_graph_id"] = "graph:forged"
        with self.assertRaisesRegex(ValueError, "TRANSITION_COMPOSE_GRAPH_MISMATCH"):
            self.compose(f=f)

    def test_policy_false_authorization_rejected(self):
        policy = copy.deepcopy(self.policy)
        policy["controls"]["safety"] = "SAFE_DELETE=PASS"
        with self.assertRaisesRegex(ValueError, "TRANSITION_POLICY_UNSAFE_GLOBAL_CONTROL"):
            self.compose(policy=policy)

    def test_retain_without_approved_replacement(self):
        target = "PhysicsFVElectronEnergyJouleHeating"
        s = copy.deepcopy(self.s)
        f = copy.deepcopy(self.f)
        s["target"] = f["target"] = target
        s["edges"][0]["to"] = s["edges"][1]["to"] = "class:" + target
        f["edges"][0]["claim_id"] = "claim:" + target + ":time_term"
        f["semantic_replacement_diffs"] = []
        result = self.compose(s=s, f=f)
        self.assertEqual(result["target_strategy"], "RETAIN_NO_APPROVED_REPLACEMENT")
        self.assertFalse(result["candidate_rewiring_options"])
        current = result["consumer_dispositions"][0]
        self.assertIn("RETAIN_UNTIL_APPROVED_OWNER", current["disposition_proposal"])
        self.assertTrue(any(b["kind"] == "NO_APPROVED_REPLACEMENT"
                            for b in result["blocking_obligations"]))
        self.assertTrue(any(step["operation"] == "RETAIN_CONSUMER_UNTIL_APPROVAL"
                            and not step["affected_paths"]
                            and not step["expected_graph_delta"]["may_remove_structural_edge_ids"]
                            for step in result["steps"]))
        self.assertFalse(any(step["operation"] == "REWIRE_CONSUMER_CANDIDATE"
                             for step in result["steps"]))

    def test_partial_shared_four_class_remains_hold(self):
        target = "PhysicsFVLogMolarElectronReactionSource"
        s, f = copy.deepcopy(self.s), copy.deepcopy(self.f)
        s["target"] = f["target"] = target
        s["edges"][0]["to"] = s["edges"][1]["to"] = "class:" + target
        f["edges"][0]["claim_id"] = "claim:" + target + ":time_term"
        f["shared_translation_unit"] = {
            "source_path": "src/Four.C",
            "co_registered_classes": [
                "PhysicsFVLogMolarElectronTimeDerivative",
                "PhysicsFVLogMolarElectronDiffusion",
                "PhysicsFVLogMolarElectrostaticDrift",
                "PhysicsFVLogMolarElectronReactionSource"],
        }
        result = self.compose(s=s, f=f)
        shared = [b for b in result["blocking_obligations"]
                  if b["kind"] == "SHARED_OWNER_MUST_BE_DISCHARGED"]
        self.assertEqual(len(shared), 3)
        self.assertEqual(result["safe_delete"], "HOLD")
        self.assertEqual(result["target_strategy"], "SHARED_FILE_INDEPENDENT_OWNER_GATES")
        f["shared_translation_unit"] = None
        with self.assertRaisesRegex(ValueError, "TRANSITION_SHARED_TRANSLATION_UNIT_MISSING"):
            self.compose(s=s, f=f)


class LiveTransitionAcceptanceP0Test(unittest.TestCase):
    """Actual exact-source join for representative Physics cases; never Native P3."""
    @classmethod
    def setUpClass(cls):
        cls.policy, cls.policy_sha = transition.load_policy(ROOT)

    def test_all_ten_profiles_cover_seven_agent_reviews(self):
        registry = functional.load_registry(ROOT)
        self.assertEqual(len(registry["profiles"]), 10)
        self.assertEqual(set(self.policy["profiles"]), set(registry["profiles"]))
        for target in sorted(registry["profiles"]):
            with self.subTest(target=target):
                p = transition.policy_for(self.policy, target)
                self.assertTrue(p["required"] and p["protected"])
                self.assertEqual(p["status"],
                                 "REVIEWED_REQUIREMENTS_NOT_VERIFIED_EXECUTION")
                self.assertEqual(registry["profiles"][target]["target"], target)

    def test_real_code6_source_join_is_hold_with_variable_density_counterexample(self):
        target = "PhysicsFVMassFractionTimeDerivative"
        s = structural.scan(ROOT, target)
        f = functional.assemble(ROOT, s, target, functional.load_registry(ROOT))
        result = transition.assemble(ROOT, s, f, target, self.policy, self.policy_sha)
        self.assertEqual(result["source_identity"]["structural_graph_id"], s["graph_id"])
        self.assertEqual(result["source_identity"]["functional_graph_id"], f["graph_id"])
        self.assertEqual(result["safe_delete"], "HOLD")
        self.assertEqual(result["numerical_equivalence"], "NOT_PROVEN")
        self.assertTrue(any("RHO_U_DOT_NOT_CONSERVATIVE" in b["required_evidence"]
                            for b in result["blocking_obligations"]))
        self.assertTrue(any(e["relation"] == "REQUIRES_EVIDENCE" for e in result["edges"]))

    def test_real_code5_four_factory_owners_not_file_retirement(self):
        target = "PhysicsFVLogMolarElectronReactionSource"
        s = structural.scan(ROOT, target)
        f = functional.assemble(ROOT, s, target, functional.load_registry(ROOT))
        result = transition.compose(s, f, self.policy, self.policy_sha)
        owners = set(result["shared_owner_contract"]["co_registered_classes"])
        self.assertEqual(len(owners), 4)
        self.assertEqual(sum(b["kind"] == "SHARED_OWNER_MUST_BE_DISCHARGED"
                             for b in result["blocking_obligations"]), 3)
        self.assertFalse(any(step["eligible_to_execute"] for step in result["steps"]))
        self.assertEqual(result["safe_delete"], "HOLD")


if __name__ == "__main__":
    unittest.main()
