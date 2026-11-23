"""#774 D11: public generated type paths, immutable rollback safety gates."""
from __future__ import annotations

import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
from issue774_d11_public_generation_rollback import (  # noqa: E402
    BASE_B, B_ELF_SHA, CASES, THERMAL, git, need,
    validate_factory_outputs, verify_rollback,
)


def layers() -> dict[str, bytes]:
    return {
        f"public_layer_{i:02d}.i": (
            f"[FVKernels]\n  [o{i}]\n    type = FVLogMolarDiffusion\n  []\n[]\n"
        ).encode()
        for i in range(11)
    }


class D11GeneratedPublicControls(unittest.TestCase):
    def test_generated_nonlegacy_input_and_separate_qpx_type(self):
        content = layers()
        content["public_layer_00.i"] += (
            b"[FVKernels]\n  [qpx]\n    type = QPXFVThermalDiffusion\n  []\n[]\n"
        )
        observed = validate_factory_outputs(
            content, {"species": {"e": {"transport_coef": {"type": "lookup"}}}})
        self.assertEqual(observed["old_thermal_factory_refs"], 0)
        self.assertIn("QPXFVThermalDiffusion", observed["actual_input_unique_types"])
        self.assertIn("lookup", observed["actual_mechanism_type_fields"])
        self.assertEqual(len(observed["output_layer_sha256"]), 11)

    def test_missing_or_legacy_generated_input_fails(self):
        values = layers()
        with self.assertRaisesRegex(ValueError, "GENERATED_LAYER_COUNT"):
            validate_factory_outputs(dict(list(values.items())[:10]), {})
        values["public_layer_01.i"] += (
            b"[FVKernels]\n  [legacy]\n    type = PhysicsFVThermalDiffusion\n  []\n[]\n"
        )
        with self.assertRaisesRegex(ValueError, "GENERATED_LEGACY_FACTORY"):
            validate_factory_outputs(values, {})

    def test_assembled_dynamic_json_type_rejected(self):
        values = layers()
        mechanism = {"drift_diffusion_boundaries": {
            "wall": {"thermal": {"type": THERMAL}}}}
        with self.assertRaisesRegex(ValueError, "GENERATED_LEGACY_FACTORY_IN_JSON"):
            validate_factory_outputs(values, mechanism)
        nonlegacy = {"drift_diffusion_boundaries": {
            "wall": {"thermal": {"type": "QPXFVThermalDiffusion"}}}}
        self.assertIn("QPXFVThermalDiffusion",
                      validate_factory_outputs(values, nonlegacy)["actual_mechanism_type_fields"])

    def test_unsupported_generated_bytes_rejected(self):
        data = layers()
        data["public_layer_00.i"] = b"type = \xff"
        with self.assertRaises(UnicodeDecodeError):
            validate_factory_outputs(data, {})

    def test_rollback_refuses_wrong_source_even_with_existing_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaisesRegex(ValueError, "CURRENT_HEAD_MISMATCH"):
                verify_rollback(ROOT, ROOT, root, root,
                                expected_head="f"*40)
            self.assertNotEqual(git(ROOT, "rev-parse", "HEAD"), BASE_B)

    def test_rollback_target_is_B_without_legacy_factory_and_no_science_claim(self):
        # B is verified source *after* retiring Thermal. Restoring any old
        # registration would be a different migration, not this rollback.
        self.assertEqual(len(CASES), 2)
        self.assertEqual(BASE_B, "c77d2f773eee96c30eeca49d7486fea22ea8e557")
        self.assertEqual(len(B_ELF_SHA), 64)
        self.assertFalse((ROOT / "physics_app/src/fvkernels/PhysicsFVThermalDiffusion.C").exists())


if __name__ == "__main__":
    unittest.main()
