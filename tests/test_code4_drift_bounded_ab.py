"""P0-only negative controls for code4's bounded A/B Native fixture driver.

These tests do not execute PhysicsApp and cannot establish scientific parity.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from experiments.code4_drift_retirement import bounded_ab as ab


class Code4BounedDriftP0(unittest.TestCase):
    def test_face_sign_carrier_upwind_and_mass_closure(self):
        ab.face_oracle()
        self.assertEqual(ab.constant_velocity(ab.CASES["charge_plus"]), 1.0)
        self.assertEqual(ab.constant_velocity(ab.CASES["charge_minus"]), -1.0)
        self.assertEqual(ab.constant_velocity(ab.CASES["carrier_two"]), 2.0)

    def test_invalid_contract_is_rejected(self):
        case = dict(ab.CASES["charge_plus"])
        for key, value in (("z", 0), ("carrier", 0), ("carrier", -1), ("mu", -1)):
            bad = dict(case)
            bad[key] = value
            with self.assertRaisesRegex(ValueError, "INVALID_BOUNDED_DRIFT_CONTRACT"):
                ab.constant_velocity(bad)

    def test_independent_implicit_fv_reference_conserves_mass(self):
        for name, case in ab.CASES.items():
            with self.subTest(name=name):
                initial = ab.independent_reference(ab.constant_velocity(case), 0)
                final = ab.independent_reference(ab.constant_velocity(case), ab.N_STEPS)
                self.assertAlmostEqual(initial["u_integral"], final["u_integral"], places=12)
                self.assertGreater(final["u_min"], 0)
                self.assertGreater(final["u_max"], final["u_min"])

    def test_generated_old_and_candidate_differ_only_at_kernel_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest = ab.prepare(folder, "0123456789abcdef")
            self.assertEqual(len(manifest["runs"]), 10)
            for name, case in ab.CASES.items():
                old = (folder / f"{name}_old.i").read_text()
                candidate = (folder / f"{name}_candidate.i").read_text()
                self.assertIn("type = PhysicsFVElectrostaticDrift", old)
                self.assertIn("type = FVAdvection", candidate)
                self.assertIn("boundaries_to_avoid = 'left right'", candidate)
                self.assertIn(f"velocity = '{ab.constant_velocity(case):.17g} 0 0'", candidate)
                self.assertIn("function = initial_profile", old)
            for item in manifest["runs"]:
                self.assertEqual(
                    hashlib.sha256((folder/item["input"]).read_bytes()).hexdigest(),
                    item["input_sha256"])

    def test_missing_or_mutated_native_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            ab.prepare(folder, "head-123")
            with self.assertRaises(FileNotFoundError):
                ab.analyze(folder, "head-123", "binary-123")
            file = folder / "charge_plus_old.i"
            file.write_text(file.read_text().replace("charge_number = 1", "charge_number = -1"))
            with self.assertRaisesRegex(ValueError, "INPUT_MUTATED"):
                ab.analyze(folder, "head-123", "binary-123")
            with self.assertRaisesRegex(ValueError, "NATIVE_EXACT_SOURCE_BINARY_MISMATCH"):
                ab.analyze(folder, "wrong-head", "binary-123")

    def test_synthetic_data_only_tests_analyzer_not_real_native(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            ab.prepare(folder, "synthetic-head")
            fields = ["time", "u_min", "u_max", "u_integral"]
            for name, case in ab.CASES.items():
                rows = []
                for index in range(ab.N_STEPS+1):
                    record = ab.independent_reference(ab.constant_velocity(case), index)
                    record["time"] = index*ab.DT
                    rows.append(record)
                for variant in ("old", "candidate"):
                    with (folder / f"{name}_{variant}_out.csv").open("w", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=fields)
                        writer.writeheader()
                        writer.writerows(rows)
            good = ab.analyze(folder, "synthetic-head", "synthetic-binary")
            self.assertEqual(good["bounded_native"], "PASS")
            self.assertEqual(good["safe_delete"], "HOLD")
            self.assertEqual(good["general_replacement"], "NOT_APPROVED")

            corrupted = folder / "charge_minus_candidate_out.csv"
            content = corrupted.read_text()
            corrupted.write_text(content.replace("1.3666666666666667", "999"))
            # A robust controlled fault that does not depend on float formatting.
            with corrupted.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            rows[1]["u_max"] = "999"
            with corrupted.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            bad = ab.analyze(folder, "synthetic-head", "synthetic-binary")
            self.assertEqual(bad["bounded_native"], "FAIL")
            self.assertTrue(any("NATIVE_AB_MISMATCH" in x for x in bad["failures"]))


if __name__ == "__main__":
    unittest.main()
