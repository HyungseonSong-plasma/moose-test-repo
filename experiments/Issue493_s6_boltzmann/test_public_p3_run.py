#!/usr/bin/env python3
"""No-Docker regression of public P3 fail-closed execution rules."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import public_p3_run as p3


class NativeP3PolicyTests(unittest.TestCase):
    def test_only_pinned_offline_oci_and_research_400(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            command = p3.native_command(p / "candidate", p / "case",
                                        [f"test_{i}.i" for i in range(10)], "417", "B")
            self.assertIn("--network", command)
            self.assertIn("none", command)
            self.assertIn(p3.p2.PINNED_OCI, command)
            self.assertIn("OXYGEN_RESEARCH_400=1", command)
            self.assertIn("Outputs/file_base=issue493_outputs/run/plasma", command[-1])
            self.assertNotIn("--check-input", command[-1])

    def test_only_approved_arm_and_full_layers(self):
        with self.assertRaises(p3.P3Error):
            p3.native_command(Path("/tmp/a"), Path("/tmp/b"), [], "417", "B")
        with self.assertRaises(p3.P3Error):
            p3.native_command(Path("/tmp/a"), Path("/tmp/b"),
                              ["x"] * 10, "941", "C")
        with self.assertRaises(p3.P3Error):
            p3.native_command(Path("/tmp/a"), Path("/tmp/b"),
                              ["x"] * 10, "other", "B")

    def test_no_silent_table_extension_and_error_separation(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "fail.log"
            f.write_text("LinearInterpolation lookup: outside allowed range")
            self.assertEqual(p3.classify_nonzero(f, 1, False), "P3_RATE_LOOKUP_DOMAIN")
            self.assertEqual(p3.classify_nonzero(f, 125, False), "P3_DOCKER_LAUNCH")
            self.assertEqual(p3.classify_nonzero(f, 1, True), "P3_TIMEOUT")
            f.write_text("nonlinear iteration failed")
            self.assertEqual(p3.classify_nonzero(f, 2, False), "P3_SOLVER_NONZERO")

    def exercise_stop(self, p2_status: str, p3_status: str | None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            control, historical, candidate = [root / x for x in
                                               ("control", "historical", "candidate")]
            mesh = historical / p3.p2.CHEM / "baseline_plasma_plus_unstructured_cover_plus_wafer.msh"
            mesh.parent.mkdir(parents=True)
            mesh.write_text("test")
            manifest = control / p3.p2.DECKS / "manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}")
            evidence = root / "p1.json"
            evidence.write_text("{}")
            opts = argparse.Namespace(
                control=control, historical=historical, candidate=candidate,
                output=root / "attempt001", p1_evidence=evidence,
                case="417", timeout_seconds=30,
            )
            with (mock.patch.object(p3.p2, "preflight", return_value={}),
                  mock.patch.object(p3.p2, "check_head"),
                  mock.patch.object(p3.p2, "stage", return_value=["x"] * 10) as stage,
                  mock.patch.object(p3.p2, "check_native", return_value={
                      "P2": p2_status, "log_sha256": "example",
                      "exit_code": 0 if p2_status == "PASS" else 2,
                      "classification": {},
                  }) as check,
                  mock.patch.object(p3, "require_p1_success",
                                    return_value={"binary_sha256": "example"}),
                  mock.patch.object(p3.p2, "sha", return_value="example"),
                  mock.patch.object(p3.shutil, "which", return_value="/usr/bin/docker"),
                  mock.patch.object(p3, "run_solve", return_value={
                      "P3": p3_status, "reason": "P3_SOLVER_NONZERO",
                  }) as solve):
                result = p3.run_case(opts)
                self.assertEqual(result["P3"], "HOLD")
                self.assertEqual(stage.call_count, 1)
                self.assertEqual(check.call_count, 1)
                self.assertEqual(solve.call_count, 0 if p3_status is None else 1)
                self.assertEqual(result["variants"]["C"]["P3"], "NOT_RUN")
                self.assertEqual(result["P4"], "NOT_RUN")
                self.assertEqual(result["science"], "SCIENCE_HOLD")
                written = json.loads((opts.output / "non_sensitive_p3_status.json").read_text())
                self.assertEqual(written["P3"], "HOLD")

    def test_failed_p2_never_starts_p3_or_c(self):
        self.exercise_stop("HOLD", None)

    def test_failed_b_p3_never_starts_c(self):
        self.exercise_stop("PASS", "FAIL")

    def test_reject_false_461_frame_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "plasma.csv"
            file.write_text("time,ne_max\n0,1\n")
            with self.assertRaisesRegex(Exception, "461"):
                p3.verify_native_csv(file)


if __name__ == "__main__":
    unittest.main(verbosity=2)
