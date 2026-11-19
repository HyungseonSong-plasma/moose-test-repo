"""P0 positive and negative controls for FDEG structural evidence."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "ci/guards/fdeg_structural.py"
spec = importlib.util.spec_from_file_location("fdeg_structural", MODULE)
assert spec and spec.loader
fdeg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fdeg)


class StructuralEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, name: str, data: str):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding="utf-8")
        return path

    def edges(self, result, relation):
        return [edge for edge in result["edges"] if edge["relation"] == relation]

    def test_factory_action_input_python_json_workflow_chain(self):
        self.put("physics_app/include/fvkernels/Legacy.h", "class Legacy : public FVKernel {};\n")
        self.put("physics_app/src/fvkernels/Legacy.C", '#include "Legacy.h"\nregisterMooseObject("PhysicsApp", Legacy);\n')
        self.put("physics_app/src/actions/LegacyAction.C", '_problem->addFVKernel("Legacy", "n", params);\n')
        self.put("tests/fixtures/base.i", "[FVKernel]\n  type = Legacy\n[]\n")
        self.put("tests/fixtures/use.i", "!include base.i\n")
        self.put("physics_harness/inputs/generator.py", 'from pathlib import Path\nconfig = {"type": "Legacy"}\nPath("tests/fixtures/base.i").write_text("type = Legacy")\n')
        self.put("tests/unit/test_legacy.py", 'def test_contract():\n    assert "Legacy" in "Legacy"\n')
        self.put("ci/guards/check_legacy.py", 'assert "Legacy"\n')
        self.put(".github/workflows/ci.yml", "jobs:\n  validate:\n    steps:\n      - run: python3 ci/guards/check_legacy.py\n")
        self.put("ci/config.json", json.dumps({"objects": [{"type": "Legacy"}]}))
        result = fdeg.scan(self.root, "Legacy")
        self.assertEqual(result["status"], "STRUCTURAL_RECORDED")
        self.assertEqual(len(self.edges(result, "REGISTERS")), 1)
        self.assertEqual(len(self.edges(result, "DECLARES")), 1)
        self.assertEqual(len(self.edges(result, "ACTION_CREATES")), 1)
        self.assertEqual(len(self.edges(result, "INPUT_INSTANTIATES")), 1)
        self.assertEqual(len(self.edges(result, "PYTHON_DECLARES_TYPE")), 1)
        self.assertEqual(len(self.edges(result, "PYTHON_WRITES_INPUT")), 1)
        self.assertEqual(len(self.edges(result, "JSON_DECLARES_TYPE")), 1)
        self.assertEqual(len(self.edges(result, "INCLUDES_INPUT")), 1)
        self.assertEqual(len(self.edges(result, "WORKFLOW_RUNS_SCRIPT")), 1)
        self.assertTrue(any(n["id"] == "file:.github/workflows/ci.yml" for n in result["nodes"]))
        self.assertTrue(all(len(e["evidence"]["blob_sha"]) == 40 and e["evidence"]["line"] >= 1
                            for e in result["edges"]))
        self.assertEqual(result["safety"], "NO_CALLER_ZERO_OR_RETIREMENT_VERDICT")

    def test_registration_is_not_runtime_instantiation(self):
        self.put("src/Legacy.C", 'registerADMooseObject("PhysicsApp", Legacy);\n')
        result = fdeg.scan(self.root, "Legacy")
        self.assertEqual(len(self.edges(result, "REGISTERS")), 1)
        self.assertEqual(self.edges(result, "INPUT_INSTANTIATES"), [])
        self.assertEqual(self.edges(result, "ACTION_CREATES"), [])

    def test_alias_input_resolves_to_target(self):
        self.put("src/Legacy.C", 'registerMooseObjectAliased("PhysicsApp", Legacy, "OldLegacy");\n')
        self.put("tests/old.i", "type = OldLegacy\n")
        result = fdeg.scan(self.root, "Legacy")
        self.assertEqual(self.edges(result, "INPUT_INSTANTIATES")[0]["detail"], "OldLegacy")
        self.assertIn("factory=OldLegacy", self.edges(result, "REGISTERS")[0]["detail"])

    def test_physics_action_registration_syntax_and_input_block(self):
        self.put("physics_app/include/physics/LegacyAction.h", "class LegacyAction : public Action {};\n")
        self.put("physics_app/src/physics/LegacyAction.C",
                 'registerPhysicsBaseTasks("PhysicsApp", LegacyAction);\n'
                 'registerMooseAction("PhysicsApp", LegacyAction, "add_kernel");\n')
        self.put("physics_app/src/base/PhysicsApp.C",
                 'registerSyntax("LegacyAction", "Physics/Plasmas/Legacy");\n')
        self.put("tests/action.i", "[Physics]\n  [./Plasmas]\n    [./Legacy]\n    [../]\n  [../]\n[]\n")
        result = fdeg.scan(self.root, "LegacyAction")
        self.assertEqual(len(self.edges(result, "REGISTERS_ACTION")), 1)
        self.assertEqual(len(self.edges(result, "REGISTERS_PHYSICS_TASKS")), 1)
        self.assertEqual(len(self.edges(result, "REGISTERS_ACTION_SYNTAX")), 1)
        self.assertEqual(len(self.edges(result, "INPUT_MATCHES_ACTION_SYNTAX")), 1)
        self.assertEqual(self.edges(result, "INPUT_INSTANTIATES"), [])

    def test_action_type_local_literal_is_candidate_not_direct(self):
        self.put("src/Legacy.C", 'registerMooseObject("PhysicsApp", Legacy);\n')
        self.put("src/Action.C", 'const auto type = "Legacy";\ngetProblem().addKernel(type, "k", params);\n')
        result = fdeg.scan(self.root, "Legacy")
        candidate = self.edges(result, "ACTION_CREATES_VIA_LOCAL_LITERAL")
        self.assertEqual(len(candidate), 1)
        self.assertEqual(candidate[0]["strength"], "LEXICAL_FLOW_CANDIDATE")
        self.assertEqual(self.edges(result, "ACTION_CREATES"), [])

    def test_dynamic_type_and_missing_include_are_not_silent_caller_zero(self):
        self.put("src/Legacy.C", 'registerMooseObject("PhysicsApp", Legacy);\n')
        self.put("input/use.i", "type = $kernel_type\n!include missing.i\n")
        self.put("generators/write.py", 'cfg = {"type": make_type()}\n')
        result = fdeg.scan(self.root, "Legacy")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(self.edges(result, "INPUT_INSTANTIATES"), [])
        self.assertIn("DYNAMIC_MOOSE_TYPE", [u["reason"] for u in result["unresolved"]])
        self.assertIn("DYNAMIC_PYTHON_TYPE", [u["reason"] for u in result["unresolved"]])
        self.assertIn("INCLUDE_UNRESOLVED:missing.i", [u["reason"] for u in result["unresolved"]])

    def test_malformed_input_is_explicit_error(self):
        self.put("src/Legacy.C", 'registerMooseObject("PhysicsApp", Legacy);\n')
        self.put("data/broken.json", '{"type": "Legacy"')
        self.put("tests/broken.py", "def oops(:\n")
        result = fdeg.scan(self.root, "Legacy")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual({e["reason"] for e in result["scan_errors"]},
                         {"JSON_PARSE_ERROR", "PYTHON_PARSE_ERROR"})

    def test_expected_sha_fail_closed(self):
        self.put("src/Legacy.C", 'registerMooseObject("PhysicsApp", Legacy);\n')
        with self.assertRaisesRegex(ValueError, "EXACT_HEAD_MISMATCH"):
            fdeg.scan(self.root, "Legacy", "a" * 40)

    def test_v02_graph_and_edge_ids_are_repeatable(self):
        self.put("src/Legacy.C", 'registerMooseObject("PhysicsApp", Legacy);\n')
        self.put("tests/case.i", "[Kernels]\n  [./one]\n    type = Legacy\n    variable = n_e\n    state_form = physical\n    block = 'bulk'\n  [../]\n[]\n")
        first = fdeg.scan(self.root, "Legacy")
        second = fdeg.scan(self.root, "Legacy")
        self.assertEqual(first["schema"], "fdeg.structural.v0.3")
        self.assertEqual(first["graph_id"], second["graph_id"])
        self.assertTrue(first["graph_id"].startswith("graph:"))
        ids = [edge["edge_id"] for edge in first["edges"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(eid.startswith("edge:") for eid in ids))
        self.assertEqual(len(first["instances"]), 1)
        inst = first["instances"][0]
        self.assertEqual(inst["block_path"], "Kernels/one")
        self.assertEqual(inst["factory_type"], "Legacy")
        self.assertEqual(inst["structural_edge_id"],
                         self.edges(first, "INPUT_INSTANTIATES")[0]["edge_id"])
        self.assertEqual(
            {p["name"]: p["raw_value"] for p in inst["bindings"]}["state_form"],
            "physical")
        self.assertEqual(
            {p["name"]: p["raw_value"] for p in inst["bindings"]}["variable"],
            "n_e")
        self.assertIn(inst["instance_id"], [n["id"] for n in first["nodes"]])
        self.assertEqual(len(self.edges(first, "DECLARES_INSTANCE")), 1)

    def test_v02_identity_changes_on_input_binding_mutation(self):
        self.put("src/Legacy.C", 'registerMooseObject("PhysicsApp", Legacy);\n')
        path = self.put("tests/case.i", "[./k]\n  type = Legacy\n  variable = n_e\n[]\n")
        first = fdeg.scan(self.root, "Legacy")
        path.write_text("[./k]\n  type = Legacy\n  variable = n_i\n[]\n", encoding="utf-8")
        second = fdeg.scan(self.root, "Legacy")
        self.assertNotEqual(first["graph_id"], second["graph_id"])
        self.assertNotEqual(first["instances"][0]["evidence"]["blob_sha"],
                            second["instances"][0]["evidence"]["blob_sha"])
        self.assertNotEqual(
            self.edges(first, "INPUT_INSTANTIATES")[0]["edge_id"],
            self.edges(second, "INPUT_INSTANTIATES")[0]["edge_id"])

    def test_v03_shared_header_build_ownership_and_coowners(self):
        self.put("physics_app/Makefile",
                 "APPLICATION_NAME := physics\ninclude $(FRAMEWORK_DIR)/app.mk\n")
        self.put("physics_app/src/fvkernels/Shared.C",
                 '#include "Shared.h"\n'
                 'registerMooseObject("PhysicsApp", Legacy);\n'
                 'registerMooseObject("PhysicsApp", AlsoShared);\n')
        self.put("physics_app/include/fvkernels/Shared.h",
                 "class Legacy : public FVKernel {};\nclass AlsoShared : public FVKernel {};\n")
        graph = fdeg.scan(self.root, "Legacy")
        self.assertEqual(graph["schema"], "fdeg.structural.v0.3")
        self.assertEqual(len(self.edges(graph, "BUILD_OWNS_SOURCE")), 1)
        self.assertEqual(len(self.edges(graph, "INCLUDES_OWNER_HEADER")), 1)
        self.assertEqual(len(self.edges(graph, "HEADER_DECLARES_TARGET")), 1)
        unit = graph["enrichment"]["shared_translation_units"][0]
        self.assertEqual(unit["registered_classes"], ["AlsoShared", "Legacy"])
        self.assertIn("REQUIRES_ALL_REGISTERED", unit["whole_file_retirement"])
        self.assertTrue(all(e["source_head"] is None and e["activation_status"] == "NOT_OBSERVED"
                            for e in graph["edges"]))

    def test_v03_declared_functor_producer_and_instance_join(self):
        self.put("src/Legacy.C", 'registerMooseObject("PhysicsApp", Legacy);\n')
        self.put("cases/runtime.i",
                 "[FunctorMaterials]\n"
                 "  [rho]\n    type = ADGenericFunctorMaterial\n"
                 "    prop_names = 'rho_const'\n  []\n[]\n"
                 "[FVKernels]\n  [t_O2p]\n    type = Legacy\n"
                 "    variable = w_O2p\n    rho = rho_const\n  []\n[]\n")
        graph = fdeg.scan(self.root, "Legacy")
        self.assertEqual(len(self.edges(graph, "BINDS_PARAMETER")), 1)
        self.assertEqual(len(self.edges(graph, "PRODUCES_FUNCTOR_CANDIDATE")), 1)
        evidence = graph["enrichment"]["provider_bindings"]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["declared_name"], "rho_const")
        self.assertEqual(evidence[0]["status"], "SAME_FILE_DECLARED_CANDIDATE")
        self.assertEqual(evidence[0]["effective_provider"], "UNKNOWN")
        self.assertEqual(graph["status"], "STRUCTURAL_RECORDED")
        self.assertIn("functor:rho_const", {n["id"] for n in graph["nodes"]})

    def test_v03_generator_map_workflow_and_unobserved_input(self):
        self.put("src/Legacy.C", 'registerMooseObject("PhysicsApp", Legacy);\n')
        self.put("scripts/build_input.py",
                 'OBJECT_TYPES = {f"FVKernels/{species}_time": "Legacy" for species in ["O2p"]}\n')
        self.put(".github/workflows/verify.yml",
                 "on: pull_request\njobs:\n  fdeg:\n    steps:\n"
                 "      - run: python3 scripts/build_input.py --static\n")
        graph = fdeg.scan(self.root, "Legacy")
        edges = self.edges(graph, "GENERATOR_EMITS_OBJECT_CANDIDATE")
        self.assertTrue(edges)
        self.assertEqual(graph["status"], "INCOMPLETE")
        self.assertTrue(any("GENERATED_INPUT_NOT_TRACKED" in x["reason"]
                            for x in graph["target_scoped_unresolved"]))
        workflow = self.edges(graph, "WORKFLOW_RUNS_SCRIPT")[0]
        self.assertEqual(workflow["workflow_context"]["job"], "fdeg")
        self.assertEqual(workflow["activation_status"], "NOT_OBSERVED")
        self.assertEqual(graph["enrichment"]["generator_routes"][0]["activation"],
                         "NOT_OBSERVED")

    def test_v03_unknown_functor_and_role_cannot_be_runtime_promoted(self):
        self.put("src/Legacy.C", 'registerMooseObject("PhysicsApp", Legacy);\n')
        self.put("tests/test_rule.py", 'def test():\n    assert "Legacy" not in "Forbidden"\n')
        self.put("cases/test.i", "[FVKernels]\n  [t]\n"
                 "    type = Legacy\n    rho = absent_rho\n  []\n[]\n")
        report = fdeg.scan(self.root, "Legacy")
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertTrue(any(e["reason"].startswith("FUNCTOR_PROVIDER_NOT_PROVEN")
                            for e in report["target_scoped_unresolved"]))
        binding = report["enrichment"]["provider_bindings"][0]
        self.assertEqual(binding["status"], "UNKNOWN")
        self.assertEqual(binding["effective_provider"], "UNKNOWN")
        lexical = [e for e in report["edges"] if e["relation"] == "MENTIONS_SYMBOL"
                   and e["evidence"]["path"] == "tests/test_rule.py"]
        self.assertTrue(lexical)
        self.assertTrue(all(e["reference_role"] == "ASSERTION_OR_PROHIBITION_NOT_RUNTIME"
                            for e in lexical))

    def test_v03_tracked_static_writer_is_not_executed_observation(self):
        self.put("src/Legacy.C", 'registerMooseObject("PhysicsApp", Legacy);\n')
        self.put("cases/input.i", "type = Legacy\n")
        self.put("scripts/build_input.py",
                 'from pathlib import Path\n'
                 'OBJECT_TYPES = {"FVKernels/test": "Legacy"}\n'
                 'Path("cases/input.i").write_text("type = Legacy")\n')
        graph = fdeg.scan(self.root, "Legacy")
        routes = graph["enrichment"]["generator_routes"]
        self.assertTrue(any(x["generated_input_path"] == "cases/input.i"
                            for x in routes))
        self.assertTrue(all(x["activation"] == "NOT_OBSERVED" for x in routes))
        self.assertEqual(graph["status"], "STRUCTURAL_RECORDED")

    def test_json_stability_and_git_blob_hash(self):
        path = self.put("src/Legacy.C", 'registerMooseObject("PhysicsApp", Legacy);\n')
        first, second = fdeg.scan(self.root, "Legacy"), fdeg.scan(self.root, "Legacy")
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(self.edges(first, "REGISTERS")[0]["evidence"]["blob_sha"],
                         fdeg.blob_sha(path.read_bytes()))


if __name__ == "__main__":
    unittest.main()
