#!/usr/bin/env python3
"""Synthetic public-data-only regression for per-run HPEM native overlays."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import tempfile
import unittest

import hpem_compare_native as hpem


class HPEMNativeOverlayTests(unittest.TestCase):
    def reference(self, root: Path, name: str, field: str, points: list[float]):
        target = root / name
        with target.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[field, "n_e_m^-3"])
            writer.writeheader()
            for pt in points:
                writer.writerow({field: pt, "n_e_m^-3": 8e16})
        return target

    def fixture(self, root: Path) -> dict:
        import numpy as np
        from scipy.io import netcdf_file

        exodus = root / "plasma.e"
        with netcdf_file(exodus, "w") as f:
            for name, count in (("time_step", 1), ("num_nodes", 4),
                                ("num_el_blk", 1), ("num_elem", 2),
                                ("num_nod_var", 1), ("len_name", 32),
                                ("num_nod_per_el1", 3)):
                f.createDimension(name, count)
            f.createVariable("time_whole", "d", ("time_step",))[:] = [1e-4]
            f.createVariable("coordx", "d", ("num_nodes",))[:] = [0, .25, 0, .25]
            f.createVariable("coordy", "d", ("num_nodes",))[:] = [0, 0, .44, .44]
            f.createVariable("connect1", "i", ("num_elem", "num_nod_per_el1"))[:] = [
                [1, 2, 3], [2, 4, 3]]
            f.createVariable("name_nod_var", "c", ("num_nod_var", "len_name"))[:] = np.asarray(
                [[b"l", b"o", b"g", b"_", b"n", b"e"] + [b" "] * 26], dtype="S1")
            f.createVariable("eb_names", "c", ("num_el_blk", "len_name"))[:] = np.asarray(
                [[b"p", b"l", b"a", b"s", b"m", b"a"] + [b" "] * 26], dtype="S1")
            f.createVariable("vals_nod_var1", "d", ("time_step", "num_nodes"))[:] = [
                [math.log(8e16 / hpem.NA)] * 4]
        csv_file = root / "plasma.csv"
        csv_file.write_text("time,ne_max\n0.0001,8e16\n")
        manifest = root / "manifest.json"
        record = {"schema": "issue493_public_p3_artifact_v1",
                  "case": "417", "arm": "B", "P3": "PASS", "science": "SCIENCE_HOLD",
                  "files": {x.name: {"sha256": hpem.sha256(x)} for x in (exodus, csv_file)}}
        manifest.write_text(json.dumps(record))
        return {"exodus": exodus, "csv_file": csv_file, "manifest_file": manifest,
                "vertical_reference": self.reference(root, "vertical.csv", "z_cm", [0, 23, 44]),
                "radial_reference": self.reference(root, "radial.csv", "r_cm", [0, 12.5, 25]),
                "output": root / "diagnostics", "label": "S6-417-B"}

    def test_complete_native_overlay_writes_expected_outputs_and_holds_science(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.fixture(Path(temp))
            result = hpem.analyze(**args)
            self.assertEqual(result["science"], "SCIENCE_HOLD")
            self.assertEqual(result["bc_p4_parity"], "NOT_EVALUATED")
            self.assertEqual(result["vertical"]["common_support_points"], 3)
            self.assertLess(result["vertical"]["rmse_over_reference_peak"], 1e-12)
            self.assertEqual(len(list(args["output"].glob("*.png"))), 4)
            self.assertEqual(len(list(args["output"].glob("*.csv"))), 2)
            self.assertTrue((args["output"] / "metrics.json").exists())
            with self.assertRaisesRegex(ValueError, "HPEM_OUTPUT_ALREADY_EXISTS"):
                hpem.analyze(**args)

    def test_fails_closed_on_reference_or_native_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.fixture(Path(temp))
            args["csv_file"].write_text("tampered")
            with self.assertRaisesRegex(ValueError, "NATIVE_OUTPUT_SHA256_MISMATCH"):
                hpem.analyze(**args)
            args["vertical_reference"].write_text("bad\n")
            with self.assertRaisesRegex(ValueError, "HPEM_REFERENCE_SCHEMA_MISMATCH"):
                hpem.load_reference(args["vertical_reference"], "z_cm")

    def test_nonfinite_and_missing_overlap_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_COMMON_PLASMA_SUPPORT"):
            hpem.evaluate([1e16, 1e16, 1e16], [float("nan")] * 3)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.reference(root, "bad.csv", "r_cm", [0, 5, 10])
            path.write_text("r_cm,n_e_m^-3\n0,1e16\n5,nan\n10,1e16\n")
            with self.assertRaisesRegex(ValueError, "HPEM_REFERENCE_NONFINITE_OR_UNORDERED"):
                hpem.load_reference(path, "r_cm")


if __name__ == "__main__":
    unittest.main(verbosity=2)
