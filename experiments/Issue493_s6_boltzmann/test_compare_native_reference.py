#!/usr/bin/env python3
"""Synthetic public-data-only regression for per-run REFERENCE native overlays."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import tempfile
import unittest

import compare_native_reference as refmod


class ReferenceNativeOverlayTests(unittest.TestCase):
    def reference(self, root: Path, name: str, field: str, points: list[float]):
        target = root / name
        with target.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[field, "n_e_m^-3"])
            writer.writeheader()
            for pt in points:
                writer.writerow({field: pt, "n_e_m^-3": 8e16})
        return target

    def fixture(self, root: Path, electron_names=("log_ne",)) -> dict:
        import numpy as np
        from scipy.io import netcdf_file

        exodus = root / "plasma.e"
        with netcdf_file(exodus, "w") as f:
            for name, count in (("time_step", 1), ("num_nodes", 4),
                                ("num_el_blk", 1), ("num_elem", 2),
                                ("num_nod_var", len(electron_names)), ("len_name", 32),
                                ("num_nod_per_el1", 3)):
                f.createDimension(name, count)
            f.createVariable("time_whole", "d", ("time_step",))[:] = [1e-4]
            f.createVariable("coordx", "d", ("num_nodes",))[:] = [0, .25, 0, .25]
            f.createVariable("coordy", "d", ("num_nodes",))[:] = [0, 0, .44, .44]
            f.createVariable("connect1", "i", ("num_elem", "num_nod_per_el1"))[:] = [
                [1, 2, 3], [2, 4, 3]]
            f.createVariable("name_nod_var", "c", ("num_nod_var", "len_name"))[:] = np.asarray(
                [[bytes([b]) for b in name.encode("ascii")] + [b" "] * (32 - len(name))
                 for name in electron_names], dtype="S1")
            f.createVariable("eb_names", "c", ("num_el_blk", "len_name"))[:] = np.asarray(
                [[b"p", b"l", b"a", b"s", b"m", b"a"] + [b" "] * 26], dtype="S1")
            for k, _name in enumerate(electron_names, 1):
                f.createVariable(f"vals_nod_var{k}", "d",
                                 ("time_step", "num_nodes"))[:] = [
                    [math.log(8e16 / refmod.NA)] * 4]
        csv_file = root / "plasma.csv"
        csv_file.write_text("time,ne_max\n0.0001,8e16\n")
        manifest = root / "manifest.json"
        record = {"schema": "issue493_public_p3_artifact_v1",
                  "case": "417", "arm": "B", "P3": "PASS", "science": "SCIENCE_HOLD",
                  "files": {x.name: {"sha256": refmod.sha256(x)} for x in (exodus, csv_file)}}
        manifest.write_text(json.dumps(record))
        return {"exodus": exodus, "csv_file": csv_file, "manifest_file": manifest,
                "vertical_reference": self.reference(root, "vertical.csv", "z_cm", [0, 23, 44]),
                "horizontal_reference": self.reference(root, "horizontal.csv", "r_cm", [0, 12.5, 25]),
                "output": root / "diagnostics", "label": "S6-417-B"}

    def test_complete_native_overlay_writes_expected_outputs_and_holds_science(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.fixture(Path(temp))
            result = refmod.analyze(**args)
            self.assertEqual(result["science"], "SCIENCE_HOLD")
            self.assertEqual(result["bc_p4_parity"], "NOT_EVALUATED")
            self.assertEqual(result["vertical"]["common_support_points"], 3)
            self.assertLess(result["vertical"]["rmse_over_reference_peak"], 1e-12)
            self.assertEqual({p.name for p in args["output"].glob("*.png")},
                             {"vertical_absolute.png", "horizontal_absolute.png"})
            self.assertEqual(len(list(args["output"].glob("*.csv"))), 2)
            self.assertTrue((args["output"] / "metrics.json").exists())
            with self.assertRaisesRegex(ValueError, "REFERENCE_OUTPUT_ALREADY_EXISTS"):
                refmod.analyze(**args)

    def test_canonical_electron_field_produces_same_scientific_hold(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.fixture(Path(temp), electron_names=("log_e",))
            result = refmod.analyze(**args)
            self.assertEqual(result["science"], "SCIENCE_HOLD")
            self.assertEqual(result["vertical"]["common_support_points"], 3)
            self.assertLess(result["horizontal"]["rmse_over_reference_peak"], 1e-12)

    def test_ambiguous_exodus_electron_names_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.fixture(Path(temp),
                                electron_names=("log_ne", "log_e"))
            with self.assertRaisesRegex(ValueError, "NATIVE_ELECTRON_STATE_AMBIGUOUS"):
                refmod.plasma_slice(args["exodus"], [0., 23., 44.],
                                   [0., 12.5, 25.], 100.)

    def test_vertical_png_uses_raw_nodes_without_changing_metrics_grid(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp:
            args = self.fixture(Path(temp))
            with patch.object(refmod, "plot_profile", wraps=refmod.plot_profile) as plot:
                result = refmod.analyze(**args)

            calls = {call.kwargs["axis"]: call for call in plot.call_args_list}
            self.assertEqual(set(calls), {"vertical", "horizontal"})
            vertical = calls["vertical"]
            self.assertEqual(vertical.args[0], [0.0, 23.0, 44.0])
            # Only the two original plasma-mesh nodes lie on r=0 in this fixture.
            self.assertEqual(vertical.args[2], [0.0, 44.0])
            self.assertEqual(len(vertical.args[3]), 2)
            for value in vertical.args[3]:
                self.assertAlmostEqual(value / 8e16, 1.0, places=12)

            # With no exact z=23 cm horizontal nodes, preserve the old
            # linear-triangle samples for the horizontal plot and both metrics.
            horizontal = calls["horizontal"]
            self.assertEqual(horizontal.args[0], horizontal.args[2])
            self.assertEqual(len(horizontal.args[3]), 3)
            for value in horizontal.args[3]:
                self.assertAlmostEqual(value / 8e16, 1.0, places=12)
            self.assertEqual(result["sampling"], "PLASMA_TRIANGLE_LINEAR_NO_EXTRAPOLATION")
            self.assertEqual(result["vertical"]["common_support_points"], 3)
            self.assertLess(result["vertical"]["rmse_over_reference_peak"], 1e-12)
            self.assertLess(result["horizontal"]["rmse_over_reference_peak"], 1e-12)

    def test_fails_closed_on_reference_or_native_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            args = self.fixture(Path(temp))
            args["csv_file"].write_text("tampered")
            with self.assertRaisesRegex(ValueError, "NATIVE_OUTPUT_SHA256_MISMATCH"):
                refmod.analyze(**args)
            args["vertical_reference"].write_text("bad\n")
            with self.assertRaisesRegex(ValueError, "REFERENCE_REFERENCE_SCHEMA_MISMATCH"):
                refmod.load_reference(args["vertical_reference"], "z_cm")

    def test_nonfinite_and_missing_overlap_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_COMMON_PLASMA_SUPPORT"):
            refmod.evaluate([1e16, 1e16, 1e16], [float("nan")] * 3)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = self.reference(root, "bad.csv", "r_cm", [0, 5, 10])
            path.write_text("r_cm,n_e_m^-3\n0,1e16\n5,nan\n10,1e16\n")
            with self.assertRaisesRegex(ValueError, "REFERENCE_REFERENCE_NONFINITE_OR_UNORDERED"):
                refmod.load_reference(path, "r_cm")

    def test_committed_reference_csv_contract(self):
        root = Path(__file__).resolve().parent / "reference"
        vertical, horizontal = root / "reference_vertical.csv", root / "reference_horizontal.csv"
        z, ne_z = refmod.load_reference(vertical, "z_cm")
        r, ne_r = refmod.load_reference(horizontal, "r_cm")
        self.assertEqual((len(z), z[0], z[-1]), (45, 0.0, 44.0))
        self.assertEqual((len(r), r[0], r[-1]), (51, 0.0, 25.0))
        self.assertEqual(max(ne_z), 8.885e16)
        self.assertEqual(max(ne_r), 8.885e16)
        self.assertEqual(ne_z[z.index(23.0)], ne_r[r.index(0.0)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
