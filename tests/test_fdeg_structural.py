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

    def test_json_stability_and_git_blob_hash(self):
        path = self.put("src/Legacy.C", 'registerMooseObject("PhysicsApp", Legacy);\n')
        first, second = fdeg.scan(self.root, "Legacy"), fdeg.scan(self.root, "Legacy")
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(self.edges(first, "REGISTERS")[0]["evidence"]["blob_sha"],
                         fdeg.blob_sha(path.read_bytes()))


if __name__ == "__main__":
    unittest.main()
