"""P0 regressions for FDEG A/B: AST roles, template instances and relevance."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
import fdeg_structural as structural  # noqa: E402
import fdeg_structural_enrichment as enrichment  # noqa: E402


class StructuralAccuracyABTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.put("src/Legacy.C", 'registerMooseObject("PhysicsApp", Legacy);\n')

    def put(self, path: str, text: str):
        output = self.root / path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        return output

    def test_assert_only_string_does_not_generate_candidate(self):
        self.put("experiments/Issue351/control.py",
                 'assert "type = Legacy" in target_input\n')
        g = structural.scan(self.root, "Legacy")
        self.assertEqual(g["enrichment"]["generator_routes"], [])
        self.assertFalse(any(e["relation"] == "GENERATOR_EMITS_OBJECT_CANDIDATE"
                             for e in g["edges"]))
        self.assertTrue(any(e["relation"] == "MENTIONS_SYMBOL" for e in g["edges"]))

    def test_argparse_type_path_is_not_dynamic_moose_object(self):
        self.put("ci/guards/audit.py",
                 'from argparse import ArgumentParser\nfrom pathlib import Path\n'
                 'p = ArgumentParser()\np.add_argument("--output", type=Path)\n')
        g = structural.scan(self.root, "Legacy")
        self.assertFalse(any(e["reason"] == "DYNAMIC_PYTHON_TYPE"
                             for e in g["unresolved"]))

    def test_literal_type_inside_real_moose_creator_is_recorded(self):
        self.put("scripts/create.py",
                 'mp.upsert_parameter("FVKernels/a", type="Legacy")\n')
        g = structural.scan(self.root, "Legacy")
        self.assertTrue(any(e["relation"] == "PYTHON_DECLARES_TYPE" for e in g["edges"]))

    def test_virtual_template_instances_are_separate_and_not_executed(self):
        self.put("physics_app/ci/build.py", '''
def render():
    return f"""[FVKernels]
  [t_O]
    type = Legacy
    variable = w_O
    rho = rho_const
  []
  [t_Om]
    type = Legacy
    variable = w_Om
    rho = rho_const
  []
[]
"""
''')
        g = structural.scan(self.root, "Legacy")
        virtual = [i for i in g["instances"]
                   if i.get("instance_kind") == "PYTHON_GENERATED_INPUT_TEMPLATE_NOT_EXECUTED"]
        self.assertEqual(len(virtual), 2)
        self.assertEqual({x["block_path"] for x in virtual},
                         {"FVKernels/t_O", "FVKernels/t_Om"})
        self.assertEqual(g["source_template_census"]["status"],
                         "SOURCE_TEMPLATE_DECLARATIONS_MAPPED_NOT_EXECUTED")
        self.assertEqual(g["source_template_census"]["mapped_virtual_instances"], 2)
        self.assertTrue(all(i["runtime_activation"] == "NOT_OBSERVED" for i in virtual))
        self.assertEqual(len([e for e in g["edges"] if e["relation"] ==
                              "PYTHON_TEMPLATE_INSTANTIATES"]), 2)

    def test_compact_type_equals_is_a_distinct_source_template_instance(self):
        self.put("physics_app/ci/compact.py", """
def render():
    return '''[FVKernels]
  [w_Om_time]
    type=Legacy
    variable=w_Om
    rho=rho_const
  []
[]
'''
""")
        g = structural.scan(self.root, "Legacy")
        rows = [i for i in g["instances"]
                if i.get("instance_kind") == "PYTHON_GENERATED_INPUT_TEMPLATE_NOT_EXECUTED"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["block_path"], "FVKernels/w_Om_time")
        self.assertEqual(g["source_template_census"]["mapped_virtual_instances"], 1)
        self.assertEqual(g["source_template_census"]["unmapped_declarations"], [])

    def test_one_space_indented_s5c_edetach_kernel_is_mapped(self):
        self.put("physics_app/ci/edetach.py", """
def render():
 return f'''[Mesh]
 [m]
  type=GeneratedMeshGenerator
 []
[]
[FVKernels]
 [wt]
  type=Legacy
  variable=w_Om
  rho=rho_const
 []
[]
'''
""")
        graph = structural.scan(self.root, "Legacy")
        found = [i for i in graph["instances"]
                 if i.get("instance_kind") ==
                 "PYTHON_GENERATED_INPUT_TEMPLATE_NOT_EXECUTED"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["block_path"], "FVKernels/wt")
        self.assertEqual(graph["source_template_census"]["mapped_virtual_instances"], 1)
        self.assertEqual(graph["source_template_census"]["unmapped_declarations"], [])
        self.assertEqual(found[0]["runtime_activation"], "NOT_OBSERVED")

    def test_unmapped_template_declaration_cannot_pass_census(self):
        self.put("physics_app/ci/unmapped.py", '''
def fake():
    return """not a full MOOSE input
    type = Legacy
    """
''')
        g = structural.scan(self.root, "Legacy")
        self.assertEqual(g["source_template_census"]["status"], "SOURCE_TEMPLATE_GAP")
        self.assertEqual(len(g["source_template_census"]["unmapped_declarations"]), 1)
        self.assertEqual(g["target_dependency_status"], "INCOMPLETE")

    def test_historical_path_is_not_historical_only(self):
        self.assertEqual(enrichment.scope("experiments/historical_recipe_support/issue192_s5r.py"),
                         "HISTORICAL_LOCATION_ACTIVITY_UNKNOWN")
        self.put("experiments/historical_recipe_support/issue192_s5r.py",
                 'CONFIG = {"FVKernels/n_e": "Legacy"}\n')
        self.put("tests/test_current.py",
                 'from experiments.historical_recipe_support.issue192_s5r import CONFIG\n')
        g = structural.scan(self.root, "Legacy")
        self.assertTrue(any(e["relation"] == "PYTHON_IMPORTS_MODULE" for e in g["edges"]))
        self.assertTrue(any(e["revision_scope"] == "HISTORICAL_LOCATION_ACTIVITY_UNKNOWN"
                            for e in g["edges"]))

    def test_unrelated_workflow_unresolved_not_target_blocker(self):
        self.put("scripts/render.py", 'TYPES = {"FVKernels/a": "Legacy"}\n')
        self.put(".github/workflows/check.yml",
                 "jobs:\n  validate:\n    steps:\n"
                 "      - run: python3 scripts/render.py\n"
                 "      - run: python3 missing/oxygen_legacy6_latest_100us.py\n")
        g = structural.scan(self.root, "Legacy")
        self.assertGreater(g["global_unresolved_count"], 0)
        self.assertEqual(g["target_scoped_unresolved_count"],
                         len(g["target_scoped_unresolved"]))
        self.assertFalse(any("oxygen_legacy6" in e["reason"]
                             for e in g["target_scoped_unresolved"]))
        self.assertEqual(g["global_scan_status"], "INCOMPLETE")


class LiveCode6CensusP0Test(unittest.TestCase):
    def test_code6_fifteen_source_declared_blocks_are_not_zero_instances(self):
        target = "PhysicsFVMassFractionTimeDerivative"
        g = structural.scan(ROOT, target)
        census = g["source_template_census"]
        # Exact 10/15 numbers were independently established in PR-A #705.
        # The graph must now enumerate the same source-backed records.
        expected = {str(p) for p in (
            "physics_app/ci/check_stage5_h05_runtime.py",
            "physics_app/ci/check_stage5_s5d_heavy_reactions.py",
            "physics_app/ci/check_standard_moose_energy_projection.py")}
        found = {x["input_path"] for x in g["instances"]
                 if x.get("instance_kind") == "PYTHON_GENERATED_INPUT_TEMPLATE_NOT_EXECUTED"}
        self.assertTrue(expected <= found)
        self.assertEqual(census["mapped_virtual_instances"], 15)
        self.assertEqual(census["unmapped_declarations"], [])
        self.assertEqual(census["runtime_coverage"], "NOT_PROVEN")


class FunctionalAndTransitionCP0Test(unittest.TestCase):
    def test_code2_invalid_molar_ev_mode_is_not_supported(self):
        import fdeg_functional as functional
        registry = functional.load_registry(ROOT)
        profile = registry["profiles"]["PhysicsFVElectronEnergyJouleHeating"]
        from test_fdeg_functional import pinned_historical_source_root
        with pinned_historical_source_root(profile) as old_root:
            params = functional.extract_parameters(old_root, profile)
        mode = next(p for p in params if p["name"] == "state_form")
        self.assertEqual(mode["allowed_enum_values"], ["normalized", "physical_eV"])
        sample = {
            "input_path": "experiments/fem_fvm_plasma_discriminator/prepare_cases.py",
            "evidence": {"blob_sha": mode["witness"]["blob_sha"]},
            "bindings": [
                {"name": "state_form", "raw_value": "molar_eV", "line": 420},
                {"name": "electron_density", "raw_value": "n_e", "line": 1},
                {"name": "potential", "raw_value": "phi", "line": 2},
                {"name": "mobility", "raw_value": "mu", "line": 3},
                {"name": "diffusion", "raw_value": "D", "line": 4}]}
        validation = functional.validate_declared_instance(sample, params)
        self.assertEqual(validation["status"], "INVALID")
        self.assertEqual(validation["mode"], "INVALID_DECLARED_MODE")
        self.assertEqual(validation["invalid"][-1]["allowed_values"],
                         ["normalized", "physical_eV"])
        sample["bindings"][0]["raw_value"] = "physical_eV"
        self.assertNotEqual(functional.validate_declared_instance(sample, params)["status"],
                            "INVALID")

    def test_transition_retain_vs_compatibility_retirement_and_no_edit(self):
        import test_fdeg_transition
        fixture = test_fdeg_transition.PureTransitionGraphP0Test()
        fixture.setUp()
        target = "PhysicsFVElectronEnergyJouleHeating"
        fixture.s["target"] = fixture.f["target"] = target
        for e in fixture.s["edges"]:
            e["to"] = "class:" + target
        fixture.f["edges"][0]["claim_id"] = "claim:" + target + ":time_term"
        fixture.f["semantic_replacement_diffs"] = []
        import fdeg_transition as transition
        result = transition.compose(fixture.s, fixture.f, fixture.policy, fixture.policy_sha)
        current = next(x for x in result["consumer_dispositions"] if x["instance_id"])
        self.assertIn("RETIRE_UNSUPPORTED_CONSUMER_WITH_EXPLICIT_APPROVAL",
                      current["disposition_options"])
        self.assertEqual(result["safe_delete"], "HOLD")
        self.assertFalse(result["change_sites"]["declared_input_and_other_consumer_paths"])
        self.assertIn("history.i", result["change_sites"]["protected_or_reference_no_edit_paths"])
        self.assertTrue(any(b["kind"] == "COMPATIBILITY_TERMINATION_NOT_APPROVED"
                            for b in result["blocking_obligations"]))
        self.assertFalse(any(step["operation"] == "REWIRE_CONSUMER_CANDIDATE"
                             for step in result["steps"]))

    def test_shared_code5_reports_file_level_four_owner_hold(self):
        import fdeg_functional as functional
        import fdeg_transition as transition
        target = "PhysicsFVLogMolarElectronReactionSource"
        s = structural.scan(ROOT, target)
        f = functional.assemble(ROOT, s, target, functional.load_registry(ROOT))
        p, sha = transition.load_policy(ROOT)
        report = transition.compose(s, f, p, sha)
        aggregate = report["shared_owner_aggregate_requirement"]
        self.assertEqual(len(aggregate["registered_classes"]), 4)
        self.assertEqual(aggregate["whole_file_safe_delete"], "HOLD")
        self.assertEqual(aggregate["required_external_manifest"],
                         "FOUR_S_F_T_REPORTS_SAME_EXACT_HEAD")


class RetirementEvidenceDP0Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import fdeg_retirement_evidence as retire
        cls.retire = retire

    def synthetic_receipt(self, root):
        retire = self.retire
        receipt = {
            "schema": retire.SCHEMA, "lifecycle": "PRE_RETIREMENT",
            "target": "Legacy", "baseline_head": "b" * 40,
            "source_blobs": {"src/Legacy.C": "old-blob"},
            "registered_owners": ["Legacy"],
            "graph_sha256": {n: "0" * 64 for n in retire.GRAPH_NAMES},
        }
        receipt["manifest_sha256"] = retire.sha256(retire.canonical(receipt))
        review = {"schema": retire.RETIRED_SCHEMA, "state": "RETIRED",
                  "target": "Legacy",
                  "baseline_manifest_sha256": receipt["manifest_sha256"],
                  "retirement_head": "c" * 40,
                  "discharged_registered_owners": ["Legacy"],
                  "external_and_generated_scope": "INDEPENDENTLY_ATTESTED",
                  "historical_protected_paths": []}
        for name in ("owner_approval_ref", "independent_native_receipt_ref",
                     "independent_coverage_receipt_ref",
                     "current_binary_compatibility_decision_ref",
                     "historical_archive_ref", "rollback_review_ref"):
            review[name] = "receipt:" + name
        return receipt, review

    def test_retired_review_cannot_skip_owner_coverage_or_prior_snapshot(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            receipt, review = self.synthetic_receipt(root)
            review["independent_native_receipt_ref"] = "UNKNOWN"
            with self.assertRaisesRegex(ValueError,
                                        "RETIREMENT_MISSING_INDEPENDENT_APPROVAL_RECEIPT"):
                self.retire.verify_retired(root, receipt, review, "c" * 40)
            review["independent_native_receipt_ref"] = "receipt:native"
            receipt["target"] = "forged"
            with self.assertRaisesRegex(ValueError, "RETIREMENT_PRE_CUT_RECEIPT_TAMPERED"):
                self.retire.verify_retired(root, receipt, review, "c" * 40)

    def test_retired_guard_rejects_source_present_and_symbol_reintroduction(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            receipt, review = self.synthetic_receipt(root)
            source = root / "src/Legacy.C"
            source.parent.mkdir(parents=True)
            source.write_text('registerMooseObject("PhysicsApp", Legacy);\n')
            with self.assertRaisesRegex(ValueError, "RETIREMENT_SOURCE_STILL_PRESENT"):
                self.retire.verify_retired(root, receipt, review, "c" * 40)
            source.unlink()
            inp = root / "cases/kept.i"
            inp.parent.mkdir(parents=True)
            inp.write_text("type = Legacy\n")
            with self.assertRaisesRegex(ValueError, "RETIREMENT_SOURCE_SYMBOL_REINTRODUCED"):
                self.retire.verify_retired(root, receipt, review, "c" * 40)

    def test_retired_guard_rejects_active_profile_and_unpinned_archive_exemption(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            receipt, review = self.synthetic_receipt(root)
            base = root / "ci/baselines"
            base.mkdir(parents=True)
            (base / "fdeg_functional_contracts.json").write_text(
                '{"profiles":{"Legacy":{"target":"Legacy"}}}')
            with self.assertRaisesRegex(ValueError, "RETIREMENT_ACTIVE_PROFILE_NOT_ARCHIVED"):
                self.retire.verify_retired(root, receipt, review, "c" * 40)
            (base / "fdeg_functional_contracts.json").unlink()
            review["historical_protected_paths"] = ["experiments/frozen.i"]
            with self.assertRaisesRegex(ValueError, "RETIREMENT_HISTORICAL_PATH_NOT_PREPINNED"):
                self.retire.verify_retired(root, receipt, review, "c" * 40)

    def test_static_retired_guard_never_returns_safe_delete_pass(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            receipt, review = self.synthetic_receipt(root)
            result = self.retire.verify_retired(root, receipt, review, "c" * 40)
            self.assertEqual(result["safe_delete"], "HOLD")
            self.assertEqual(result["caller_zero_reverified_here"],
                             "NOT_PROVEN_BY_THIS_STATIC_GUARD")

    def test_exact_historical_electron_capture_and_archive_graph_joins(self):
        from test_fdeg_functional import pinned_historical_graph_root, HISTORICAL_HEAD
        with pinned_historical_graph_root() as old_root:
            receipt, docs = self.retire.capture(old_root, "PhysicsFVElectronReactionSource",
                                                 HISTORICAL_HEAD)
        self.retire.verify_snapshot(receipt, docs)
        self.assertEqual(receipt["safe_delete"], "HOLD")
        self.assertEqual(receipt["baseline_head"], HISTORICAL_HEAD)
        self.assertIn("physics_app/src/fvkernels/PhysicsFVElectronReactionSource.C",
                      receipt["source_blobs"])
        docs["transition"]["safe_delete"] = "PASS"
        with self.assertRaisesRegex(ValueError, "RETIREMENT_GRAPH_CONTENT_MISMATCH"):
            self.retire.verify_snapshot(receipt, docs)

    def test_exact_head_live_shared_electron_capture_keeps_hold(self):
        head = structural.git(ROOT, "rev-parse", "HEAD")
        receipt, docs = self.retire.capture(ROOT, "PhysicsFVLogMolarElectronReactionSource", head)
        self.retire.verify_snapshot(receipt, docs)
        self.assertEqual(receipt["baseline_head"], head)
        self.assertEqual(receipt["safe_delete"], "HOLD")
        self.assertEqual(len(receipt["registered_owners"]), 4)
        self.assertIn("physics_app/src/fvkernels/PhysicsFVLogMolarElectronTransport.C",
                      receipt["source_blobs"])


if __name__ == "__main__":
    unittest.main()
