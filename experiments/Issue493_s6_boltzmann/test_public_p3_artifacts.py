#!/usr/bin/env python3
"""No-Docker regression for raw-output artifact gates and P4 numeric telemetry."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import archive_public_p3_results as archive
import p4_compare_public_bc as p4


class PublicArtifactContractTests(unittest.TestCase):
    def dataset(self, root: Path, arm: str = "B") -> tuple:
        case = "417"
        output = root / f"{case}_{arm}" / "issue493_outputs" / "run"
        output.mkdir(parents=True)
        csv_file = output / "plasma.csv"
        with csv_file.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time", "ne", "O2p"])
            for i in range(461):
                writer.writerow([i * 1e-4 / 460, 1 + i, 2 + i])
        # Mimic only the NetCDF file signature; the real P4 job opens NetCDF
        # and rejects malformed/empty Exodus, unlike this output-copy unit test.
        exodus = output / "plasma.e"
        exodus.write_bytes(b"CDF\x01" + b"0" * 80)
        dig = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        record = {
            "schema": "issue493_public_p3_native_v2", "case": case,
            "mode": f"complete-{arm.lower()}",
            "source_sha": archive.SOURCE, "candidate_sha": archive.CANDIDATE,
            "oci_image": archive.OCI, "P0": "PASS", "P1": "PASS",
            "P2": "HOLD", "P3": "HOLD", "P4": "NOT_RUN",
            "science": "SCIENCE_HOLD", "p2_passed_arms": [arm],
            "p3_passed_arms": [arm], "variants": {
                arm: {
                    "P2": "PASS", "P3": "PASS", "frames": 461,
                    "t_end_seconds": 1e-4, "exit_code": 0,
                    "termination": "EXIT", "timed_out": False,
                    "timeout_budget_seconds": 20400,
                    "p1_binary_sha256": "a" * 64,
                    "native_exodus_sha256": dig(exodus),
                    "native_exodus_bytes": exodus.stat().st_size,
                    "native_csv_sha256": dig(csv_file),
                    "native_csv_bytes": csv_file.stat().st_size,
                },
                ("C" if arm == "B" else "B"): {
                    "P2": "NOT_RUN", "P3": "NOT_RUN",
                },
            },
        }
        return record, output

    def test_archive_only_exodus_csv_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            status, _ = self.dataset(root)
            path = root / "status.json"
            path.write_text(json.dumps(status))
            published = root / "publish"
            manifest = archive.publish(path, root, published, "417", "B")
            self.assertEqual({p.name for p in published.iterdir()},
                             {"plasma.csv", "plasma.e", "manifest.json"})
            self.assertEqual(manifest["frames"], 461)
            self.assertEqual(manifest["P3"], "PASS")
            self.assertEqual(manifest["science"], "SCIENCE_HOLD")
            with self.assertRaisesRegex(ValueError, "ARCHIVE_ROOT_ALREADY_EXISTS"):
                archive.publish(path, root, published, "417", "B")

    def test_reject_false_completion_and_tampered_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data, folder = self.dataset(root, "C")
            data["variants"]["C"]["frames"] = 460
            with self.assertRaisesRegex(ValueError, "FULL_NATIVE_COMPLETION_NOT_PROVEN"):
                archive.inspect(data, root, "417", "C")
            data["variants"]["C"]["frames"] = 461
            (folder / "plasma.csv").write_text("time,ne\n0,1\n")
            with self.assertRaisesRegex(ValueError, "OUTPUT_PROVENANCE_MISMATCH"):
                archive.inspect(data, root, "417", "C")

    def test_p4_csv_detects_all_461_points_and_numeric_difference(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _, bdir = self.dataset(root / "b", "B")
            _, cdir = self.dataset(root / "c", "C")
            result, b, c = p4.compare_csv(bdir / "plasma.csv", cdir / "plasma.csv")
            self.assertEqual(result["timepoints"], 461)
            self.assertEqual(result["fields_compared"], 2)
            self.assertEqual(result["field_metrics"]["ne"]["max_abs"], 0)
            self.assertEqual(len(b), 461)
            self.assertEqual(len(c), 461)
            with (cdir / "plasma.csv").open("a") as f:
                f.write("0.000101,462,463\n")
            with self.assertRaisesRegex(ValueError, "P4_INCOMPLETE_CSV"):
                p4.compare_csv(bdir / "plasma.csv", cdir / "plasma.csv")

    def test_c_handoff_carries_test_lib_and_checks_runtime_closure(self):
        workflow = (Path(__file__).resolve().parents[2] /
                    ".github/workflows/issue493-public-bc-results-p4-once.yml").read_text()
        self.assertIn('test -e candidate/physics_app/test/lib/libphysics_test-opt.so.0', workflow)
        self.assertIn('tar -C candidate/physics_app -czf "$DIR/app-lib.tar.gz" lib test/lib', workflow)
        self.assertIn("ISSUE493_C_SHARED_LIBRARY_CLOSURE_PASS", workflow)
        self.assertIn("ldd /app/physics_app/physics-opt", workflow)
    def test_cannot_claim_full_scientific_parity_from_p4_metrics(self):
        self.assertIn("HOLD_NO_APPROVED_TOLERANCES",
                      Path(p4.__file__).read_text())
        self.assertNotIn("private_rates", Path(archive.__file__).read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
