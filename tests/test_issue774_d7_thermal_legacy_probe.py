"""D7 public-only controls: Native outcome classifier, fixture, artifact provenance."""
from __future__ import annotations
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
from issue774_thermal_legacy_probe import (  # noqa: E402
    TARGET, UNKNOWN, classify, make_cases, stage,
)


class LegacyThermalW1Test(unittest.TestCase):
    def test_positive_and_missing_object_have_distinct_outcomes(self):
        self.assertEqual(classify(0, "Syntax OK", TARGET), "SYNTAX_OK")
        self.assertEqual(classify(1, TARGET + " is not registered", TARGET),
                         "FACTORY_NOT_AVAILABLE")
        self.assertEqual(classify(1, UNKNOWN + " is not registered", UNKNOWN),
                         "FACTORY_NOT_AVAILABLE")
        self.assertEqual(classify(1, "cannot load shared library", TARGET),
                         "UNEXPECTED_NATIVE_RESULT")
        self.assertEqual(classify(1, "Syntax OK", TARGET),
                         "UNEXPECTED_NATIVE_RESULT")

    def test_on_off_and_unknown_are_distinct_exact_variants(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            original = root / "original.i"
            original.write_text("type = PhysicsFVThermalDiffusion\n"
                                "include_thermal_diffusion = true\n")
            digest = make_cases(original, root / "cases")
            self.assertEqual(len(set(digest.values())), 3)
            self.assertIn(TARGET, (root / "cases/on.i").read_text())
            self.assertIn("include_thermal_diffusion = false",
                          (root / "cases/off.i").read_text())
            self.assertIn(UNKNOWN, (root / "cases/unknown.i").read_text())

    def test_mismatched_identity_never_stages_binary(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "identity.json").write_text('{"source_head":"0","run_id":"invalid"}')
            with self.assertRaisesRegex(ValueError, "D7_W1_PROVENANCE_MISMATCH"):
                stage(root, root / "staging", "A")


if __name__ == "__main__":
    unittest.main()
