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

    def test_v2_cpu_quota_clamps_affinity(self):
        group = Path(self.tmp.name) / "cpu_cgroup"
        group.mkdir()
        (group / "cpu.max").write_text("150000 100000\n")
        with patch.object(harness.os, "sched_getaffinity", return_value=set(range(32))):
            self.assertEqual(harness.available_cpus(group), 2)
        (group / "cpu.max").write_text("max 100000\n")
        with patch.object(harness.os, "sched_getaffinity", return_value=set(range(4))):
            self.assertEqual(harness.available_cpus(group), 4)

    def test_v1_cpu_quota_fallback_and_malformed_data(self):
        group = Path(self.tmp.name) / "cpu_cgroup"
        (group / "cpu").mkdir(parents=True)
        (group / "cpu/cpu.cfs_quota_us").write_text("200000\n")
        (group / "cpu/cpu.cfs_period_us").write_text("100000\n")
        self.assertEqual(harness.quota_cpus(group), 2)
        (group / "cpu/cpu.cfs_quota_us").write_text("-1\n")
        self.assertIsNone(harness.quota_cpus(group))
        (group / "cpu.max").write_text("invalid\n")
        self.assertIsNone(harness.quota_cpus(group))

    def test_storage_preflight_fails_closed_for_space_and_inodes(self):
        from types import SimpleNamespace
        with (patch.object(harness.shutil, "disk_usage", return_value=SimpleNamespace(free=100)),
              patch.object(harness.os, "statvfs",
                           return_value=SimpleNamespace(f_files=1000, f_favail=1000))):
            with self.assertRaises(harness.NativeBuildError) as raised:
                harness.check_build_storage(self.app, min_free_bytes=1024)
            self.assertEqual(raised.exception.classification, "DISK_CAPACITY_INSUFFICIENT")
        with (patch.object(harness.shutil, "disk_usage", return_value=SimpleNamespace(free=10_000)),
              patch.object(harness.os, "statvfs",
                           return_value=SimpleNamespace(f_files=1000, f_favail=4))):
            with self.assertRaises(harness.NativeBuildError) as raised:
                harness.check_build_storage(self.app, min_free_bytes=1024, min_free_inodes=200)
            self.assertEqual(raised.exception.classification, "INODE_CAPACITY_INSUFFICIENT")
        with (patch.object(harness.shutil, "disk_usage", return_value=SimpleNamespace(free=10_000)),
              patch.object(harness.os, "statvfs",
                           return_value=SimpleNamespace(f_files=0, f_favail=0))):
            result = harness.check_build_storage(self.app, min_free_bytes=1024, min_free_inodes=200)
            self.assertIsNone(result["free_inodes"])

    def test_storage_thresholds_cannot_be_negative(self):
        with self.assertRaises(harness.NativeBuildError) as raised:
            harness.check_build_storage(self.app, min_free_bytes=-1)
        self.assertEqual(raised.exception.classification, "INVALID_STORAGE_POLICY")

    def test_extended_failures_are_terminal_before_unity_retry(self):
        unity = "build/unity_src/kernels_Unity.C:21: error: redefinition of 'x'\n"
        cases = {
            "LINKER_SYMBOL_FAILURE": "ld: undefined reference to 'PhysicsSomething'",
            "RUNTIME_ABI_MISMATCH": "libfoo.so: version GLIBCXX_3.4.99 not found",
            "DISK_CAPACITY_EXHAUSTED": "fatal error: No space left on device",
            "RESOURCE_EXHAUSTION": "c++: fatal error: Killed signal terminated program cc1plus",
            "HEADER_OR_GENERATED_FILE_MISSING": "fatal error: PhysicsGenerated.h: No such file or directory",
            "SHELL_QUOTING_OR_UNSET_VARIABLE": "bash: $2: unbound variable",
        }
        for category, message in cases.items():
            with self.subTest(category=category):
                self.assertEqual(harness.classify_failure(unity + message), category)
                self.assertEqual(harness.collision_directories(unity + message, self.app), ())

    def test_unity_directory_detection_rejects_symlink_vendor_escape(self):
        external = Path(self.tmp.name) / "vendor"
        external.mkdir()
        (self.app / "src/escape").symlink_to(external, target_is_directory=True)
        log = "build/unity_src/escape_Unity.C:1: error: redefinition of 'x'"
        self.assertEqual(harness.classify_failure(log), "APP_UNITY_SYMBOL_COLLISION")
        self.assertEqual(harness.collision_directories(log, self.app), ())

    def test_no_vendor_cleanup_is_attempted_on_resource_errors(self):
        error, report, calls = self._build_with_fake_make([
            ("c++: fatal error: Killed signal terminated program cc1plus", 137)
        ])
        self.assertEqual(report["classification"], "RESOURCE_EXHAUSTION")
        self.assertEqual(len(calls), 1)
        self.assertTrue(all("clean" not in " ".join(argv) for argv in calls))

    def test_ignored_stale_application_cache_rejected_without_cleanup(self):
        (self.root / ".git").mkdir()
        cache = self.app / "build"
        cache.mkdir()
        (cache / "persisted-object.o").write_bytes(b"do-not-delete")
        with (patch.object(harness.subprocess, "run"),
              patch.object(harness.subprocess, "check_output", side_effect=["a" * 40 + "\n", ""])):
            with self.assertRaises(harness.NativeBuildError) as raised:
                harness._verify_source(self.root, "a" * 40, self.app / "physics-opt")
        self.assertEqual(raised.exception.classification, "STALE_APP_BUILD_CACHE")
        self.assertEqual((cache / "persisted-object.o").read_bytes(), b"do-not-delete")

    def test_preflight_mismatched_sha_and_dirty_app_rejected(self):
        with self.assertRaisesRegex(harness.NativeBuildError, "40 lowercase"):
            harness._verify_source(self.root, "bad", self.app / "physics-opt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
