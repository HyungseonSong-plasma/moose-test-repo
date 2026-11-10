"""Offline regression tests for the application-only Native P1 build harness."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from physics_harness.execution import native_build as harness


class NativeBuildHarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "checkout"
        self.app = self.root / "physics_app"
        (self.app / "src" / "utils").mkdir(parents=True)
        (self.app / "src" / "kernels").mkdir(parents=True)

    def test_jobs_are_bounded_by_memory_and_cpu(self):
        self.assertEqual(harness.choose_jobs(64, 2_000_000, 4), 1)
        self.assertEqual(harness.choose_jobs(64, 8_000_000, 4), 2)
        self.assertEqual(harness.choose_jobs(64, 20_000_000, 4), 4)
        self.assertEqual(harness.choose_jobs(2, 20_000_000, 4), 2)
        with self.assertRaises(ValueError):
            harness.choose_jobs(4, 20_000_000, 0)

    def test_cgroup_memory_limit_overrides_host_ram(self):
        proc = Path(self.tmp.name) / "meminfo"
        proc.write_text("MemAvailable: 32000000 kB\n")
        cg = Path(self.tmp.name) / "cgroup"
        cg.mkdir()
        (cg / "memory.max").write_text("10000000000\n")
        (cg / "memory.current").write_text("6000000000\n")
        self.assertEqual(harness.available_memory_kb(proc, cg), 4_000_000_000 // 1024)

    def test_make_only_uses_application_unity_scope(self):
        dirs = harness.resolve_scoped_dirs(self.app, ["src/utils"])
        command = harness.make_argv(self.app, 2, dirs)
        self.assertIn("MOOSE_UNITY=true", command)
        self.assertIn("app_non_unity_dirs=" + str((self.app / "src/utils").resolve()), command)
        self.assertNotIn("MOOSE_UNITY=false", " ".join(command))
        self.assertEqual(command[0], "make")
        self.assertEqual(command[3], "-j2")

    def test_rejects_vendor_escape_symlink_or_missing_scope(self):
        with self.assertRaisesRegex(harness.NativeBuildError, "non-unity directory"):
            harness.resolve_scoped_dirs(self.app, ["../moose"])
        with self.assertRaises(harness.NativeBuildError):
            harness.resolve_scoped_dirs(self.app, ["/opt/physics_vendor/squirrel"])
        with self.assertRaises(harness.NativeBuildError):
            harness.resolve_scoped_dirs(self.app, ["src/unknown"])
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (self.app / "src" / "escape").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(harness.NativeBuildError):
            harness.resolve_scoped_dirs(self.app, ["src/escape"])

    def test_classifies_old_incidents_without_auto_vendor_rebuild(self):
        self.assertEqual(
            harness.classify_failure(
                "/opt/physics_vendor/squirrel/src/kernels/PotentialAdvection.C:20:"
                " invalid use of incomplete type 'class FEProblemBase'"),
            "VENDOR_SOURCE_OR_ABI_FAILURE",
        )
        self.assertEqual(
            harness.classify_failure("build/unity_src/utils_Unity.C:21: error: redefinition of 'operator'"),
            "APP_UNITY_SYMBOL_COLLISION",
        )
        self.assertEqual(
            harness.classify_failure("shell: line 2: $2: unbound variable"),
            "SHELL_QUOTING_OR_UNSET_VARIABLE",
        )
        self.assertEqual(
            harness.classify_failure("kernel.C:12: error: invalid template expression"),
            "SOURCE_COMPILATION_FAILURE",
        )

    def _build_with_fake_make(self, lines, *, profile="auto", max_attempts=3):
        calls = []

        def fake_logged(command, *, cwd, log, timeout_s):
            calls.append(list(command))
            log.parent.mkdir(parents=True, exist_ok=True)
            text, result = lines[len(calls) - 1]
            log.write_text(text)
            if result == 0:
                binary = self.app / "physics-opt"
                binary.write_bytes(b"mock native binary")
                binary.chmod(0o755)
            return result

        report_path = Path(self.tmp.name) / "report.json"
        with (patch.object(harness, "_verify_source"),
              patch.object(harness, "_verify_vendor_environment"),
              patch.object(harness, "available_cpus", return_value=8),
              patch.object(harness, "available_memory_kb", return_value=20_000_000),
              patch.object(harness, "_run_logged", side_effect=fake_logged)):
            try:
                result = harness.build(
                    source_root=self.root,
                    expected_sha="a" * 40,
                    log_dir=Path(self.tmp.name) / "logs",
                    report_path=report_path,
                    profile=profile,
                    max_attempts=max_attempts,
                )
                return result, json.loads(report_path.read_text()), calls
            except harness.NativeBuildError as exc:
                return exc, json.loads(report_path.read_text()), calls

    def test_auto_profile_avoids_known_utils_collision_on_first_attempt(self):
        result, report, calls = self._build_with_fake_make([("ok", 0)])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(report["attempts"][0]["attempt"], 1)
        self.assertIn("src/utils", str(calls[0]))
        self.assertEqual(len(calls), 1)

    def test_auto_retries_only_new_application_unity_dir(self):
        first_log = (
            "In file included from build/unity_src/kernels_Unity.C:21:\n"
            "src/kernels/Example.C:4: error: redefinition of 'local_helper'\n"
        )
        result, report, calls = self._build_with_fake_make([(first_log, 2), ("ok", 0)])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(calls), 2)
        self.assertIn(str((self.app / "src/kernels").resolve()), str(calls[1]))
        self.assertIn(str((self.app / "src/utils").resolve()), str(calls[1]))
        self.assertNotIn("MOOSE_UNITY=false", str(calls[1]))
        self.assertEqual(report["attempts"][0]["classification"], "APP_UNITY_SYMBOL_COLLISION")

    def test_other_compile_error_is_not_retried_or_reclassified_success(self):
        result, report, calls = self._build_with_fake_make(
            [("kernel.C:1: error: unknown class", 1)])
        self.assertIsInstance(result, harness.NativeBuildError)
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["classification"], "SOURCE_COMPILATION_FAILURE")
        self.assertEqual(len(calls), 1)

    def test_vendor_error_fails_closed_without_retry(self):
        result, report, calls = self._build_with_fake_make(
            [("/opt/physics_vendor/squirrel/src/kernels/PotentialAdvection.C:20:"
              " invalid use of incomplete type 'class FEProblemBase'", 1)])
        self.assertEqual(report["classification"], "VENDOR_SOURCE_OR_ABI_FAILURE")
        self.assertEqual(len(calls), 1)

    def test_scoped_profile_does_not_retry(self):
        result, report, calls = self._build_with_fake_make([
            ("build/unity_src/kernels_Unity.C:10: error: redefinition of 'x'", 1)
        ], profile="scoped")
        self.assertEqual(report["classification"], "APP_UNITY_SYMBOL_COLLISION")
        self.assertEqual(len(calls), 1)

    def test_retry_budget_and_duplicate_unity_conflict_fail_closed(self):
        result, report, calls = self._build_with_fake_make([
            ("build/unity_src/kernels_Unity.C:10: error: redefinition of 'x'", 1)
        ], max_attempts=1)
        self.assertEqual(report["classification"], "RETRY_BUDGET_EXHAUSTED")
        self.assertEqual(len(calls), 1)

    def test_preflight_mismatched_sha_and_dirty_app_rejected(self):
        with self.assertRaisesRegex(harness.NativeBuildError, "40 lowercase"):
            harness._verify_source(self.root, "bad", self.app / "physics-opt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
