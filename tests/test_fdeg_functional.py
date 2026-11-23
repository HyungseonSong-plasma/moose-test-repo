"""FDEG Functional v0.1 P0: source identity, graph join, and semantic negatives."""
from __future__ import annotations

import copy
import importlib.util
from contextlib import contextmanager
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


@contextmanager
def historical_thermal_source():
    """Only historical-source assertions may read the deleted C++ Factory."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        archived = (ROOT / "docs/development/archive/issue774_retired_factories/"
                    "PhysicsFVThermalDiffusion.C.txt")
        destination = root / "physics_app/src/fvkernels/PhysicsFVThermalDiffusion.C"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(archived.read_bytes())
        yield root


class FunctionalP0Test(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.put("src/Legacy.C",
            'registerMooseObject("PhysicsApp", Legacy);\n'
            'InputParameters Legacy::validParams()\n'
            '{\n  return FVElementalKernel::validParams();\n}\n'
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
        self.profile["discriminator_contracts"] = {
            name: {"setup": "same signed source under controlled mutation",
                   "observable": "residual and Jacobian",
                   "expected": "detect any missing source, sign or AD scale",
                   "status": "NOT_EVALUATED", "measured_run_id": None,
                   "acceptance_tolerance": "OWNER_UNSPECIFIED"}
            for name in self.profile["required_discriminators"]
        }
        self.profile["preservation_contract"] = {
            "applicability": "IF_ACTIVATED_ONLY", "equation_term_owner": "electron_continuity",
            "removal_effect": "signed residual lost if active",
            "representation_and_state": "normalized source",
            "required_producer_names": ["number_source"],
            "coupled_guards": ["AD/Jacobian signed source"],
            "explicit_refusals": ["runtime unverified"],
            "claim_ids": ["residual"],
            "effective_runtime_status": "UNKNOWN",
            "science_acceptance": "NOT_EVALUATED"}
        dimensions = {
            key: {"incumbent": "R=-source/scale", "candidate_expected": "UNKNOWN",
                  "parity_status": "NOT_EVALUATED"}
            for key in ("representation", "residual_formula", "sign", "units",
                        "time_state", "face_and_boundary", "interpolation_and_limiter",
                        "ad_jacobian", "parameters_and_defaults", "source_owner")}
        self.profile["alternatives"][0]["comparison_contract"] = {
            "status": "CANDIDATE_UNVERIFIED",
            "decision": "HOLD",
            "runtime_evidence": "NOT_OBSERVED",
            "dimensions": dimensions,
            "candidate_source": {"source_status": "NOT_LOCALLY_SOURCE_VERIFIED"},
            "equivalence_class": "NUMERIC_UNVERIFIED",
            "incumbent_claim_ids": ["residual"],
            "documented_conditions": ["same functor"],
            "known_counterexamples": ["AD mismatch"],
            "measured_residual_jacobian": "NOT_EVALUATED",
            "tolerance": "OWNER_UNSPECIFIED"}
        self.registry = {"schema": "fdeg.functional_registry.v0.2",
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
        self.assertEqual(result["schema"], "fdeg.functional.v0.2")
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
        self.assertEqual(consumers[0]["effective_runtime_binding"], "UNKNOWN")
        self.assertEqual(result["equivalence_verdict"], "NOT_PROVEN")
        self.assertEqual(len(result["discriminator_contracts"]), 3)
        self.assertTrue(all(x["status"] == "NOT_EVALUATED"
                            for x in result["discriminator_contracts"].values()))
        self.assertTrue(result["parameter_declarations"] == [])

    def test_v02_declared_functor_binding_is_not_effective_provider(self):
        self.put("cases/electron.i",
            "[FunctorMaterials]\n  [src]\n    type = ADGenericFunctorMaterial\n"
            "    prop_names = 'rate'\n  []\n[]\n"
            "[Kernels]\n  [electron]\n    type = Legacy\n"
            "    variable = n_e\n    number_source = rate\n  []\n[]\n")
        graph = structural.scan(self.root, "Legacy")
        result = self.assemble(graph=graph)
        binding = next(b for b in result["producer_binding_graph"]
                       if b["parameter"] == "number_source")
        self.assertEqual(binding["status"], "SAME_FILE_DECLARED_CANDIDATE")
        self.assertEqual(binding["effective_provider"], "UNKNOWN")
        owned = [e for e in result["edges"]
                 if e["relation"] == "EQUATION_TERM_OWNER_CONDITIONAL"]
        self.assertEqual(len(owned), 1)
        self.assertEqual(owned[0]["runtime_status"], "NOT_OBSERVED")
        self.assertTrue(any(e["relation"] == "EFFECTIVE_FUNCTIONAL_BINDING_CANDIDATE"
                            for e in result["edges"]))

    def test_v02_forged_provider_candidate_rejected_after_rehash(self):
        self.put("cases/electron.i",
            "[Kernels]\n  [electron]\n    type = Legacy\n"
            "    number_source = rate\n  []\n[]\n")
        graph = structural.scan(self.root, "Legacy")
        forged = copy.deepcopy(graph)
        self.assertTrue(forged["enrichment"]["provider_bindings"])
        forged["enrichment"]["provider_bindings"][0]["status"] = "RUNTIME_CONFIRMED"
        forged["graph_id"] = structural.stable_id(
            "graph", {k: v for k, v in forged.items() if k != "graph_id"})
        with self.assertRaisesRegex(ValueError, "STRUCTURAL_ENRICHMENT_SOURCE_RECONSTRUCTION_MISMATCH"):
            self.assemble(graph=forged)

    def test_v02_replacement_dimension_promotion_fails_closed(self):
        forged = copy.deepcopy(self.registry)
        dimensions = forged["profiles"]["Legacy"]["alternatives"][0][
            "comparison_contract"]["dimensions"]
        dimensions["sign"]["parity_status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "FUNCTIONAL_REPLACEMENT_DIMENSION_FALSE_PASS"):
            self.assemble(registry=forged)

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

    def test_forged_declared_binding_rejected_even_if_graph_id_rehashed(self):
        graph = copy.deepcopy(self.graph)
        binding = next(x for x in graph["instances"][0]["bindings"]
                       if x["name"] == "state_form")
        binding["raw_value"] = "physical"
        graph["graph_id"] = structural.stable_id(
            "graph", {k: v for k, v in graph.items() if k != "graph_id"})
        with self.assertRaisesRegex(ValueError, "STRUCTURAL_BINDING_WITNESS_MISMATCH"):
            self.assemble(graph=graph)

    def test_legacy_schema_target_and_wrong_head_rejected(self):
        tampered = copy.deepcopy(self.graph)
        tampered["schema"] = "fdeg.structural.v0.1"
        with self.assertRaisesRegex(ValueError, "STRUCTURAL_SCHEMA_OR_TARGET_MISMATCH"):
            self.assemble(graph=tampered)
        with self.assertRaisesRegex(ValueError, "STRUCTURAL_EXACT_HEAD_MISMATCH"):
            functional.assemble(self.root, self.graph, "Legacy",
                                self.registry, "a" * 40)

    def test_missing_discriminator_contract_rejected(self):
        tampered = copy.deepcopy(self.registry)
        tampered["profiles"]["Legacy"]["discriminator_contracts"].pop("AD_JACOBIAN")
        with self.assertRaisesRegex(ValueError, "FUNCTIONAL_DISCRIMINATOR_CONTRACT_INCOMPLETE"):
            self.assemble(registry=tampered)

    def test_discriminator_forged_runtime_pass_rejected(self):
        tampered = copy.deepcopy(self.registry)
        tampered["profiles"]["Legacy"]["discriminator_contracts"]["SIGN_FLIP"]["status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "FUNCTIONAL_DISCRIMINATOR_CANNOT_ASSERT_PASS"):
            self.assemble(registry=tampered)

    def test_no_registry_equivalence_promotion(self):
        tampered = copy.deepcopy(self.registry)
        tampered["profiles"]["Legacy"]["alternatives"][0]["status"] = "NUMERICALLY_VALIDATED"
        with self.assertRaisesRegex(ValueError, "FUNCTIONAL_ALTERNATIVE_CANNOT_ASSERT_EQUIVALENCE"):
            self.assemble(registry=tampered)

    def test_incomplete_structural_scan_is_not_caller_zero(self):
        self.put("cases/unknown.i", "type = $dynamic_type\n")
        graph = structural.scan(self.root, "Legacy")
        self.assertEqual(graph["status"], "INCOMPLETE")
        self.assertEqual(graph["target_dependency_status"],
                         "DECLARATIONS_ONLY_RUNTIME_UNVERIFIED")
        result = self.assemble(graph=graph)
        self.assertEqual(result["global_scan_status"], "INCOMPLETE")
        self.assertEqual(result["target_dependency_status"],
                         "DECLARATIONS_ONLY_RUNTIME_UNVERIFIED")
        self.assertNotIn("STRUCTURAL_TARGET_DEPENDENCIES_INCOMPLETE",
                         result["unresolved_obligations"])
        self.assertEqual(result["equivalence_verdict"], "NOT_PROVEN")
        self.assertEqual(result["safety"],
                         "NO_CALLER_ZERO_TRANSITION_OR_RETIREMENT_AUTHORIZATION")


class LiveContractsP0Test(unittest.TestCase):
    def test_six_source_pinned_profiles_and_anchors(self):
        registry = functional.load_registry(ROOT)
        self.assertEqual(len(registry["profiles"]), 10)
        for target, profile in sorted(registry["profiles"].items()):
            with self.subTest(target=target):
                functional.validate_registry_profile(profile)
                if target == "PhysicsFVThermalDiffusion":
                    # Historical profile remains pinned, but is not live in New-only.
                    with historical_thermal_source() as old_root:
                        witnesses, blobs = functional.source_witnesses(old_root, profile)
                        parameters = functional.extract_parameters(old_root, profile)
                else:
                    witnesses, blobs = functional.source_witnesses(ROOT, profile)
                    parameters = functional.extract_parameters(ROOT, profile)
                self.assertTrue(witnesses)
                self.assertIn(profile["source"]["path"], blobs)
                self.assertTrue(all(w["line_start"] >= 1 for w in witnesses))
                self.assertTrue(profile["required_discriminators"])
                self.assertTrue(profile["unresolved_semantics"])
                self.assertEqual(set(profile["required_discriminators"]),
                                 set(profile["discriminator_contracts"]))
                self.assertTrue(parameters)

    def test_v02_live_candidate_source_witness_and_variable_density_blocker(self):
        registry = functional.load_registry(ROOT)
        mass = registry["profiles"]["PhysicsFVMassFractionTimeDerivative"]
        candidate = mass["alternatives"][0]
        witnesses = functional.validate_candidate_source(ROOT, candidate)
        self.assertTrue(witnesses)
        self.assertEqual(witnesses[0]["support"],
                         "CANDIDATE_SOURCE_EXPRESSION_NOT_EQUIVALENCE")
        self.assertIn("rho_n-rho_old", candidate["comparison_contract"][
            "dimensions"]["residual_formula"]["candidate_expected"])
        self.assertEqual(candidate["comparison_contract"]["decision"], "HOLD")
        self.assertEqual(candidate["comparison_contract"]["runtime_evidence"],
                         "NOT_OBSERVED")

    def test_v02_code5_shared_file_and_semantic_diff_all_hold(self):
        registry = functional.load_registry(ROOT)
        target = "PhysicsFVLogMolarElectronReactionSource"
        result = functional.assemble(ROOT, structural.scan(ROOT, target),
                                     target, registry)
        self.assertEqual(result["schema"], "fdeg.functional.v0.2")
        self.assertEqual(result["shared_file_retirement_requirement"],
                         "ALL_REGISTERED_CLASSES_MUST_BE_DISCONNECTED")
        self.assertEqual(result["replacement_verdict"], "ALL_CANDIDATES_UNVERIFIED")
        self.assertTrue(all(x["transition_permission"] == "HOLD"
                            for x in result["semantic_replacement_diffs"]))
        self.assertTrue(result["build_and_header_ownership"]["translation_units"])

    def test_code5_four_classes_share_one_file_but_distinct_contracts(self):
        registry = functional.load_registry(ROOT)
        names = [
            "PhysicsFVLogMolarElectronTimeDerivative",
            "PhysicsFVLogMolarElectronDiffusion",
            "PhysicsFVLogMolarElectrostaticDrift",
            "PhysicsFVLogMolarElectronReactionSource"]
        params = {}
        for name in names:
            profile = registry["profiles"][name]
            unit = functional.shared_unit_evidence(ROOT, profile)
            self.assertEqual(set(unit["co_registered_classes"]), set(names))
            self.assertEqual(unit["status"], "GROUP_REGISTERED_NOT_RETIRED")
            params[name] = {p["name"] for p in functional.extract_parameters(ROOT, profile)}
        self.assertIn("vector_tags", params[names[0]])
        self.assertNotIn("coeff", params[names[0]])
        self.assertIn("coeff", params[names[1]])
        self.assertIn("use_element_gradient_for_potential", params[names[2]])
        self.assertEqual(params[names[3]], {"number_source"})

    def test_code5_claim_cannot_use_another_class_method_as_witness(self):
        registry = functional.load_registry(ROOT)
        profile = copy.deepcopy(
            registry["profiles"]["PhysicsFVLogMolarElectronTimeDerivative"])
        profile["claims"][0]["anchors"] = [
            "return -physical_number_source / avogadro_per_mol;"]
        with self.assertRaisesRegex(ValueError, "FUNCTIONAL_SOURCE_ANCHOR_MISSING"):
            functional.source_witnesses(ROOT, profile)

    def test_code5_structural_join_has_shared_owner_edges(self):
        target = "PhysicsFVLogMolarElectronReactionSource"
        graph = structural.scan(ROOT, target)
        result = functional.assemble(ROOT, graph, target,
                                     functional.load_registry(ROOT))
        self.assertEqual(result["shared_translation_unit"]["status"],
                         "GROUP_REGISTERED_NOT_RETIRED")
        self.assertEqual(
            sum(e["relation"] == "SHARES_TRANSLATION_UNIT_WITH"
                for e in result["edges"]), 3)
        self.assertEqual(result["equivalence_verdict"], "NOT_PROVEN")

    def test_optional_description_is_not_default(self):
        doc = functional.load_registry(ROOT)
        source = functional.extract_parameters(
            ROOT, doc["profiles"]["PhysicsFVElectronReactionSource"])
        params = {p["name"]: p for p in source}
        self.assertTrue(params["state_form"]["has_explicit_source_default"])
        self.assertFalse(params["n_ref"]["has_explicit_source_default"])
        self.assertFalse(params["number_source"]["has_explicit_source_default"])
        self.assertTrue(params["number_source"]["required"])
        with historical_thermal_source() as old_root:
            thermal = functional.extract_parameters(
                old_root, doc["profiles"]["PhysicsFVThermalDiffusion"])
        switch = next(p for p in thermal if p["name"] == "include_thermal_diffusion")
        self.assertTrue(switch["has_explicit_source_default"])

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
