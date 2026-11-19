"""code7 G2 input-census negative controls; no Native execution or historical edits."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "code7_s6_final_input_census", ROOT / "ci/guards/code7_s6_final_input_census.py")
assert spec is not None and spec.loader is not None
census = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census)


class Code7FinalInputCensusP0Test(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stage = Path(self.temp.name)
        self.chem = self.stage / census.CHEM
        self.chem.mkdir(parents=True)

    def write(self, name: str, text: str) -> None:
        (self.chem / name).write_text(text, encoding="utf-8")

    def test_no_current_type_does_not_promote_caller_zero(self):
        self.write("layer.i", "[FVKernels]\n  [transport]\n    type = FVReaction\n  []\n[]\n")
        result = census.census_layers(self.stage, ["layer.i"])
        self.assertFalse(result["declared_current"])
        self.assertFalse(result["declared_historical_qpx"])
        self.assertEqual(result["file_count"], 1)

    def test_current_factory_detected_and_historical_is_distinct(self):
        self.write("layer.i", "[FVKernels]\n  [a]\n    type = PhysicsFVThermalDiffusion\n  []\n"
                              "  [b]\n    type = QPXFVThermalDiffusion\n  []\n[]\n")
        result = census.census_layers(self.stage, ["layer.i"])
        self.assertEqual(len(result["declared_current"]), 1)
        self.assertEqual(len(result["declared_historical_qpx"]), 1)

    def test_include_closure_does_not_hide_a_target(self):
        self.write("layer.i", "!include imported.i\n[FVKernels]\n[]\n")
        self.write("imported.i", "[FVKernels]\n  [active]\n"
                                 "    type = PhysicsFVThermalDiffusion\n  []\n[]\n")
        result = census.census_layers(self.stage, ["layer.i"])
        self.assertEqual(result["file_count"], 2)
        self.assertEqual(len(result["declared_current"]), 1)

    def test_dynamic_type_fails_closed(self):
        self.write("layer.i", "[FVKernels]\n  [candidate]\n"
                              "    type = ${DYNAMIC_FACTORY}\n  []\n[]\n")
        result = census.census_layers(self.stage, ["layer.i"])
        self.assertFalse(result["declared_current"])
        self.assertEqual(result["unresolved_type_or_include"][0]["reason"],
                         "NONLITERAL_TYPE")

    def test_missing_include_and_escape_are_rejected(self):
        self.write("layer.i", "!include other.i\n")
        with self.assertRaisesRegex(ValueError, "G2_INPUT_MISSING"):
            census.census_layers(self.stage, ["layer.i"])
        self.write("other.i", "!include ../../../../../../etc/passwd\n")
        with self.assertRaisesRegex(ValueError, "G2_UNSAFE_LAYER_PATH"):
            census.census_layers(self.stage, ["layer.i"])

    def test_manifest_sha_is_not_native_approval(self):
        self.assertEqual(census.TARGET, "PhysicsFVThermalDiffusion")
        self.assertEqual(census.HISTORICAL, "QPXFVThermalDiffusion")
        self.assertEqual(census.CASES, ("417", "941"))


if __name__ == "__main__":
    unittest.main()
