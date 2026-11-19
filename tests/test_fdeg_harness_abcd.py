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
        self.assertGreaterEqual(census["mapped_virtual_instances"], 15)
        self.assertEqual(census["unmapped_declarations"], [])
        self.assertEqual(census["runtime_coverage"], "NOT_PROVEN")


if __name__ == "__main__":
    unittest.main()
