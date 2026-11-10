#!/usr/bin/env python3
"""Public P3 controls: no private data or Docker required."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import p3_diagnostics as diag
import public_p3_run as p3


class NativeP3PolicyTests(unittest.TestCase):
    def test_reviewed_source_and_no_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            command = p3.native_command(p / "candidate", p / "case",
                                        [f"input_{i}.i" for i in range(10)], "417", "B")
            self.assertIn("--network", command)
            self.assertIn("none", command)
            self.assertIn(p3.p2.PINNED_OCI, command)
            self.assertIn("OXYGEN_RESEARCH_400=1", command)
            self.assertIn("OXYGEN_RESEARCH_QUICK_5MIN=0", command)
            self.assertIn("Outputs/file_base=issue493_outputs/run/plasma", command[-1])
            self.assertNotIn("--check-input", command[-1])

    def test_reject_wrong_input_arm_or_implicit_lookup_expansion(self):
        with self.assertRaises(p3.P3Error):
            p3.native_command(Path("/tmp/a"), Path("/tmp/b"), [], "417", "B")
        with self.assertRaises(p3.P3Error):
            p3.native_command(Path("/tmp/a"), Path("/tmp/b"), ["x"] * 10, "941", "C")
        with self.assertRaises(p3.P3Error):
            p3.native_command(Path("/tmp/a"), Path("/tmp/b"), ["x"] * 10, "other", "B")
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "failure.log"
            log.write_text("LinearInterpolation lookup: outside allowed range")
            self.assertEqual(p3.classify_nonzero(log, 1, False), "P3_RATE_LOOKUP_DOMAIN")
            log.write_text("nonlinear iteration failed")
            self.assertEqual(p3.classify_nonzero(log, 2, False), "P3_SOLVER_NONZERO")

    def make_inputs(self, root: Path, *, mode: str):
        control, historical, candidate = [root / x for x in ("control", "historical", "candidate")]
        mesh = historical / p3.p2.CHEM / "baseline_plasma_plus_unstructured_cover_plus_wafer.msh"
        mesh.parent.mkdir(parents=True)
        mesh.write_text("PUBLIC-ONLY MESH MOCK")
        manifest = control / p3.p2.DECKS / "manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("{}")
        evidence = root / "p1.json"
        evidence.write_text("{}")
        return argparse.Namespace(
            control=control, historical=historical, candidate=candidate,
            output=root / "attempt001", p1_evidence=evidence, case="417",
            timeout_seconds=60, mode=mode, authorize_full_p3=mode == "full",
        )

    def test_b_p2_pass_b_p3_timeout_does_not_run_c_and_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            opts = self.make_inputs(Path(tmp), mode="full")
            with (mock.patch.object(p3.p2, "preflight", return_value={}),
                  mock.patch.object(p3.p2, "check_head"),
                  mock.patch.object(p3.p2, "stage", return_value=["x"] * 10) as stage,
                  mock.patch.object(p3.p2, "check_native", return_value={
                      "P2": "PASS", "log_sha256": "p2hash", "exit_code": 0,
                      "classification": {"status": "PASS"},
                  }) as check,
                  mock.patch.object(p3, "require_p1_success",
                                    return_value={"binary_sha256": "binaryhash"}),
                  mock.patch.object(p3.p2, "sha", return_value="example"),
                  mock.patch.object(p3.shutil, "which", return_value="/usr/bin/docker"),
                  mock.patch.object(p3, "run_solve", return_value={
                      "P3": "HOLD", "reason": "P3_TIMEOUT", "exit_code": None,
                      "last_reported_step": 17, "timed_out": True,
                  }) as solve):
                report = p3.run_case(opts)
                self.assertEqual(stage.call_count, 1)
                self.assertEqual(check.call_count, 1)
                self.assertEqual(solve.call_count, 1)
            self.assertEqual(report["P0"], "PASS")
            self.assertEqual(report["P1"], "PASS")
            self.assertEqual(report["p2_passed_arms"], ["B"])
            self.assertEqual(report["p2_not_run_arms"], ["C"])
            self.assertEqual(report["P2"], "HOLD")  # Aggregate not false PASS
            self.assertEqual(report["variants"]["B"]["P2"], "PASS")
            self.assertIsNone(report["variants"]["B"]["exit_code"])
            self.assertEqual(report["variants"]["C"]["P2"], "NOT_RUN")
            self.assertEqual(report["variants"]["C"]["P3"], "NOT_RUN")
            self.assertEqual(report["P3"], "HOLD")
            self.assertEqual(report["P4"], "NOT_RUN")
            self.assertEqual(report["science"], "SCIENCE_HOLD")
            saved = json.loads((opts.output / "non_sensitive_p3_status.json").read_text())
            self.assertEqual(saved["p2_passed_arms"], ["B"])

    def test_diagnostic_runs_only_b_even_if_b_finishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            opts = self.make_inputs(Path(tmp), mode="diagnostic")
            with (mock.patch.object(p3.p2, "preflight", return_value={}),
                  mock.patch.object(p3.p2, "check_head"),
                  mock.patch.object(p3.p2, "stage", return_value=["x"] * 10) as stage,
                  mock.patch.object(p3.p2, "check_native", return_value={
                      "P2": "PASS", "log_sha256": "p2hash", "exit_code": 0,
                      "classification": {"status": "PASS"},
                  }),
                  mock.patch.object(p3, "require_p1_success",
                                    return_value={"binary_sha256": "binaryhash"}),
                  mock.patch.object(p3.p2, "sha", return_value="example"),
                  mock.patch.object(p3.shutil, "which", return_value="/usr/bin/docker"),
                  mock.patch.object(p3, "run_solve", return_value={
                      "P3": "PASS", "reason": None, "frames": 461,
                  }) as solve):
                report = p3.run_case(opts)
                self.assertEqual(stage.call_count, 1)
                self.assertEqual(solve.call_count, 1)
            self.assertEqual(report["variants"]["C"]["P2"], "NOT_RUN")
            self.assertEqual(report["P3"], "HOLD")
            self.assertEqual(report["p3_passed_arms"], ["B"])

    def test_complete_b_success_never_starts_c_or_claims_b_c_parity(self):
        with tempfile.TemporaryDirectory() as tmp:
            opts = self.make_inputs(Path(tmp), mode="complete-b")
            with (mock.patch.object(p3.p2, "preflight", return_value={}),
                  mock.patch.object(p3.p2, "check_head"),
                  mock.patch.object(p3.p2, "stage", return_value=["x"] * 10) as stage,
                  mock.patch.object(p3.p2, "check_native", return_value={
                      "P2": "PASS", "log_sha256": "p2hash", "exit_code": 0,
                      "classification": {"status": "PASS"},
                  }),
                  mock.patch.object(p3, "require_p1_success",
                                    return_value={"binary_sha256": "binaryhash"}),
                  mock.patch.object(p3.p2, "sha", return_value="example"),
                  mock.patch.object(p3.shutil, "which", return_value="/usr/bin/docker"),
                  mock.patch.object(p3, "run_solve", return_value={
                      "P3": "PASS", "reason": None, "frames": 461,
                      "t_end_seconds": 0.0001, "exit_code": 0,
                      "timed_out": False,
                  }) as solve):
                report = p3.run_case(opts)
                self.assertEqual(stage.call_count, 1)
                self.assertEqual(solve.call_count, 1)
            self.assertEqual(report["variants"]["B"]["P3"], "PASS")
            self.assertEqual(report["variants"]["C"]["P3"], "NOT_RUN")
            self.assertEqual(report["P3"], "HOLD")
            self.assertEqual(report["P4"], "NOT_RUN")
            self.assertEqual(report["science"], "SCIENCE_HOLD")
            self.assertEqual(report["p3_passed_arms"], ["B"])

    def test_complete_b_requires_explicit_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            opts = self.make_inputs(Path(tmp), mode="complete-b")
            opts.authorize_full_p3 = False
            with self.assertRaisesRegex(p3.P3Error, "FULL_P3_EXPLICIT_ACK_REQUIRED"):
                p3.run_case(opts)

    def test_missing_p2_stops_before_solver(self):
        with tempfile.TemporaryDirectory() as tmp:
            opts = self.make_inputs(Path(tmp), mode="full")
            with (mock.patch.object(p3.p2, "preflight", return_value={}),
                  mock.patch.object(p3.p2, "check_head"),
                  mock.patch.object(p3.p2, "stage", return_value=["x"] * 10),
                  mock.patch.object(p3.p2, "check_native", return_value={
                      "P2": "HOLD", "log_sha256": "p2hash", "exit_code": 2,
                      "classification": {"status": "HOLD"},
                  }),
                  mock.patch.object(p3, "require_p1_success",
                                    return_value={"binary_sha256": "binaryhash"}),
                  mock.patch.object(p3.p2, "sha", return_value="example"),
                  mock.patch.object(p3.shutil, "which", return_value="/usr/bin/docker"),
                  mock.patch.object(p3, "run_solve") as solve):
                report = p3.run_case(opts)
                solve.assert_not_called()
            self.assertEqual(report["P3"], "HOLD")
            self.assertEqual(report["variants"]["C"]["P3"], "NOT_RUN")

    def test_explicit_full_gate_and_bounded_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            opts = self.make_inputs(Path(tmp), mode="full")
            opts.authorize_full_p3 = False
            with self.assertRaisesRegex(p3.P3Error, "FULL_P3_EXPLICIT_ACK_REQUIRED"):
                p3.run_case(opts)
            opts.mode = "diagnostic"
            opts.timeout_seconds = 901
            with self.assertRaisesRegex(p3.P3Error, "DIAGNOSTIC_BUDGET_EXCEEDS"):
                p3.run_case(opts)

    def test_reject_incomplete_native_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "plasma.csv"
            file.write_text("time,ne_max\n0,1\n")
            with self.assertRaisesRegex(Exception, "461"):
                p3.verify_native_csv(file)


class SanitizedTelemetryTests(unittest.TestCase):
    def test_parser_only_reports_observed_steps(self):
        raw = ("Time Step 1, time = 2.17391e-07, dt=2e-07\n"
               "noise token private_rate = SHOULD_NOT_LEAK\n"
               "Time Step 45, time = 9.78261e-06\n"
               "Time Step 777, time = 2e-4\n")
        result = diag.parse_step_progress(raw)
        self.assertEqual(result["last_reported_step"], 45)
        self.assertAlmostEqual(result["last_reported_time_seconds"], 9.78261e-06)
        self.assertNotIn("SHOULD_NOT_LEAK", str(result))
        self.assertEqual(diag.parse_step_progress("not a MOOSE time step"),
                         {"last_reported_step": None,
                          "last_reported_time_seconds": None})

    def test_unavailable_stats_never_fabricate_resource_usage(self):
        with mock.patch.object(diag.subprocess, "run", side_effect=OSError):
            self.assertEqual(diag.docker_resources("issue493-p3-417-b"),
                             {"cpu_percent": None, "memory_bytes": None})
        with self.assertRaises(ValueError):
            diag.docker_resources("not-approved-identifier")

    def test_monitored_timeout_has_null_exit_not_fabricated_127(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cmd = [sys.executable, "-c", "import time; print('Time Step 4, time = 1e-6', flush=True); time.sleep(5)"]
            with (mock.patch.object(diag, "docker_resources",
                                    return_value={"cpu_percent": None,
                                                  "memory_bytes": None}),
                  mock.patch.object(diag, "_stop_container",
                                    side_effect=lambda name, proc: (proc.kill(), proc.wait(timeout=3)))):
                status = diag.monitor_solver(
                    cmd, cwd=root, log=root / "native.log",
                    case="417", variant="B",
                    timeout_seconds=1, heartbeat_seconds=1,
                )
            self.assertTrue(status["timed_out"])
            self.assertIsNone(status["returncode"])
            self.assertEqual(status["termination"], "TIMEOUT")
            self.assertEqual(status["last_reported_step"], 4)

    def test_completed_command_keeps_true_exit_and_no_fake_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cmd = [sys.executable, "-c", "print('Time Step 2, time = 4e-7', flush=True); raise SystemExit(7)"]
            status = diag.monitor_solver(
                cmd, cwd=root, log=root / "native.log", case="941",
                variant="B", timeout_seconds=5, heartbeat_seconds=1,
            )
            self.assertEqual(status["returncode"], 7)
            self.assertFalse(status["timed_out"])
            self.assertEqual(status["termination"], "EXIT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
