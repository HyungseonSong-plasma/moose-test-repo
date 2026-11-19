"""FDEG exact-HEAD scanner cache: repeatability, invalidation and fail closed."""
from __future__ import annotations

import contextlib
import gzip
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
import fdeg_structural as structural  # noqa: E402
import fdeg_scan_cache as cache  # noqa: E402


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True, text=True, check=True)
    return result.stdout.strip()


class ScanCacheP0Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repository"
        self.cache_dir = Path(self.tmp.name) / "runner-cache"
        self.root.mkdir()
        git(self.root, "init", "-q")
        (self.root / "src").mkdir()
        (self.root / "cases").mkdir()
        (self.root / "src" / "Legacy.C").write_text(
            'registerMooseObject("PhysicsApp", Legacy);\n')
        (self.root / "cases" / "input.i").write_text(
            "[FVKernels]\n  [legacy]\n    type = Legacy\n"
            "    variable = n_e\n  []\n[]\n")
        git(self.root, "add", ".")
        git(self.root, "-c", "user.email=ci@example.invalid",
            "-c", "user.name=FDEG CI", "commit", "-q", "-m", "fixture")
        self.head = git(self.root, "rev-parse", "HEAD")
        self.env = mock.patch.dict(os.environ, {
            "FDEG_CACHE_DIR": str(self.cache_dir)}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

    def scan(self, expected_head=None):
        with contextlib.redirect_stderr(io.StringIO()) as captured:
            result = structural.scan(self.root, "Legacy", expected_head)
        return result, captured.getvalue()

    def test_first_miss_then_hit_without_listing_or_reading_tracked_files(self):
        initial, first_log = self.scan(self.head)
        self.assertIn("FDEG_STRUCTURAL_CACHE=MISS_STORED", first_log)
        self.assertEqual(initial["safety"], "NO_CALLER_ZERO_OR_RETIREMENT_VERDICT")
        self.assertEqual(initial["scan_scope"]["files_scanned"], 2)
        with mock.patch.object(structural, "tracked_files",
                               side_effect=AssertionError("full rescan prohibited")):
            again, cached_log = self.scan(self.head)
        self.assertIn("FDEG_STRUCTURAL_CACHE=HIT", cached_log)
        self.assertEqual(initial, again)
        self.assertEqual(initial["graph_id"], again["graph_id"])

    def test_second_target_uses_full_head_source_index_without_file_rescan(self):
        original, first_log = self.scan(self.head)
        self.assertIn("FDEG_SOURCE_INDEX=MISS_STORED", first_log)
        sources = list(self.cache_dir.glob("sources-*.json.gz"))
        self.assertEqual(len(sources), 1)
        with mock.patch.object(structural, "tracked_files",
                               side_effect=AssertionError("full file listing forbidden")):
            with contextlib.redirect_stderr(io.StringIO()) as output:
                other = structural.scan(self.root, "Other", self.head)
        self.assertIn("FDEG_SOURCE_INDEX=HIT", output.getvalue())
        self.assertIn("FDEG_STRUCTURAL_CACHE=MISS_STORED", output.getvalue())
        self.assertEqual(other["scan_scope"]["files_scanned"],
                         original["scan_scope"]["files_scanned"])
        self.assertEqual(other["safety"], "NO_CALLER_ZERO_OR_RETIREMENT_VERDICT")
        with mock.patch.dict(os.environ, {"FDEG_CACHE_DIR": ""}):
            independent = structural.scan(self.root, "Other", self.head)
        self.assertEqual(other, independent)
        self.assertEqual(other["graph_id"], independent["graph_id"])

    def test_broken_shared_source_index_rescans_instead_of_silently_skipping(self):
        self.scan(self.head)
        index, = list(self.cache_dir.glob("sources-*.json.gz"))
        index.write_bytes(b"corrupt gzip content")
        with contextlib.redirect_stderr(io.StringIO()) as output:
            other = structural.scan(self.root, "Other", self.head)
        self.assertIn("FDEG_SOURCE_INDEX=MISS_STORED", output.getvalue())
        self.assertEqual(other["scan_scope"]["files_scanned"], 2)
        self.assertEqual(other["safety"], "NO_CALLER_ZERO_OR_RETIREMENT_VERDICT")

    def test_rehashed_source_index_missing_one_file_is_not_complete(self):
        self.scan(self.head)
        index, = list(self.cache_dir.glob("sources-*.json.gz"))
        record = json.loads(gzip.decompress(index.read_bytes()))
        record["payload"]["contents"].pop("cases/input.i")
        record["payload_sha256"] = cache.digest(
            cache.canonical(record["payload"]))
        index.write_bytes(gzip.compress(cache.canonical(record), mtime=0))
        with contextlib.redirect_stderr(io.StringIO()) as output:
            other = structural.scan(self.root, "Other", self.head)
        # An attacker rehashed the JSON but cannot make a missing Git source
        # pass the HEAD's tracked-file/blob completeness check.
        self.assertIn("FDEG_SOURCE_INDEX=MISS_STORED", output.getvalue())
        self.assertEqual(other["scan_scope"]["files_scanned"], 2)
        self.assertEqual(other["safety"], "NO_CALLER_ZERO_OR_RETIREMENT_VERDICT")

    def test_dirty_tracked_source_rejects_exact_head_and_never_reads_cache(self):
        self.scan(self.head)
        with (self.root / "cases" / "input.i").open("a") as stream:
            stream.write("  [another]\n    type = Legacy\n  []\n")
        with self.assertRaisesRegex(ValueError, "TRACKED_WORKTREE_DIRTY"):
            self.scan(self.head)
        changed, log = self.scan()
        self.assertNotIn("FDEG_STRUCTURAL_CACHE=HIT", log)
        self.assertGreater(len(changed["instances"]), 1)

    def test_new_git_commit_changes_cache_key(self):
        before, first = self.scan(self.head)
        (self.root / "cases" / "input.i").write_text(
            "[FVKernels]\n  [legacy]\n    type = Legacy\n"
            "    variable = n_e\n    rho = rho_const\n  []\n[]\n")
        git(self.root, "add", ".")
        git(self.root, "-c", "user.email=ci@example.invalid",
            "-c", "user.name=FDEG CI", "commit", "-q", "-m", "changed")
        next_head = git(self.root, "rev-parse", "HEAD")
        self.assertNotEqual(self.head, next_head)
        with self.assertRaisesRegex(ValueError, "EXACT_HEAD_MISMATCH"):
            self.scan(self.head)
        after, second = self.scan(next_head)
        self.assertIn("FDEG_STRUCTURAL_CACHE=MISS_STORED", second)
        self.assertNotEqual(before["graph_id"], after["graph_id"])
        self.assertEqual(len(list(self.cache_dir.glob("structural-*.json"))), 2)

    def test_corrupt_cache_and_forged_graph_hash_trigger_fresh_scan(self):
        original, _ = self.scan(self.head)
        path, = list(self.cache_dir.glob("structural-*.json"))
        record = json.loads(path.read_text())
        record["report"]["safety"] = "SAFE_DELETE=PASS"
        path.write_text(json.dumps(record))
        rebuilt, log = self.scan(self.head)
        self.assertIn("FDEG_STRUCTURAL_CACHE=MISS_STORED", log)
        self.assertEqual(rebuilt, original)
        path.write_text("{broken cache")
        again, log = self.scan(self.head)
        self.assertIn("FDEG_STRUCTURAL_CACHE=MISS_STORED", log)
        self.assertEqual(again, original)

    def test_scanner_implementation_fingerprint_forces_new_cache(self):
        before, _ = self.scan(self.head)
        extra = Path(self.tmp.name) / "new-code.py"
        extra.write_text("# version 2\n")
        original_key = cache.cache_key
        with mock.patch.object(
                cache, "cache_key",
                side_effect=lambda root, head, target, paths:
                original_key(root, head, target, paths + (extra,))):
            after, log = self.scan(self.head)
        self.assertIn("FDEG_STRUCTURAL_CACHE=MISS_STORED", log)
        self.assertEqual(after, before)
        self.assertEqual(len(list(self.cache_dir.glob("structural-*.json"))), 2)

    def test_no_opt_in_has_no_implicit_cache(self):
        with mock.patch.dict(os.environ, {"FDEG_CACHE_DIR": ""}):
            first = structural.scan(self.root, "Legacy", self.head)
            again = structural.scan(self.root, "Legacy", self.head)
        self.assertEqual(first, again)
        self.assertFalse(self.cache_dir.exists())

    def test_cache_does_not_change_unknown_consumer_or_retirement_verdict(self):
        initial, _ = self.scan(self.head)
        reused, log = self.scan(self.head)
        self.assertIn("HIT", log)
        self.assertEqual(initial["target_dependency_status"],
                         reused["target_dependency_status"])
        self.assertEqual(initial["global_unresolved_count"],
                         reused["global_unresolved_count"])
        self.assertEqual(initial["safety"], "NO_CALLER_ZERO_OR_RETIREMENT_VERDICT")
        self.assertFalse(any("SAFE_DELETE=PASS" in str(v)
                             for v in reused.values()))


if __name__ == "__main__":
    unittest.main()
