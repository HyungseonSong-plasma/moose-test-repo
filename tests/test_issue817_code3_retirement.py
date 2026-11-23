"""Fail-closed Code3 pre-retirement source and active-consumer gates (#817)."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
import issue817_code3_retirement as code3  # noqa: E402


class Code3RetiredSourceCensus(unittest.TestCase):
    def test_real_exact_head_proves_tracked_factory_cut_and_migrated_routes(self):
        head = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                       cwd=ROOT, text=True).strip()
        result = code3.audit(ROOT, head)
        self.assertEqual(result["schema"], code3.SCHEMA)
        self.assertTrue(result["source_cut_applied"])
        self.assertFalse(result["safe_delete"])  # until post-cut W1/Native acceptance
        self.assertEqual(result["active_consumer_migration"],
                         "TRACKED_NEWONLY_CONSUMERS_MIGRATED_PENDING_NATIVE")
        self.assertTrue(result["post_cut_contract"]["retired_cpp_absent"])
        self.assertGreaterEqual(result["post_cut_contract"]["migrated_consumer_count"], 8)
        self.assertEqual(result["post_cut_contract"]["old_factory_active_references"], [])
        self.assertIn(code3.HISTORIC_GENERATOR, code3.CURRENT_POSITIVE_ROUTES)

    def test_stale_head_and_invalid_head_rejected(self):
        with self.assertRaisesRegex(ValueError, "EXACT_HEAD_MISMATCH"):
            code3.audit(ROOT, "f" * 40)
        with self.assertRaisesRegex(ValueError, "BAD_HEAD"):
            code3.audit(ROOT, "main")

    def test_active_paths_not_misclassified_as_historical(self):
        self.assertEqual(code3.classify(code3.HISTORIC_GENERATOR),
                         "GENERATOR_POTENTIAL_UNRESOLVED")
        self.assertEqual(code3.classify("physics_app/ci/sample.i"),
                         "MOOSE_INPUT_CONSUMER")
        self.assertEqual(code3.classify("physics_app/ci/sample.py"),
                         "ACTIVE_CI_CONSUMER_OR_GUARD")
        self.assertEqual(code3.classify("docs/foo.md"), "DOC_REFERENCE")
        self.assertEqual(code3.classify("tests/test.py"), "TEST_REFERENCE")

    def test_source_and_candidates_cannot_be_missing_or_modified(self):
        tracked = {p: {"sha": sha, "mode": "100644"} for p, sha in
                   ((code3.SRC, code3.SRC_BLOB), (code3.HDR, code3.HDR_BLOB),
                    (code3.RUNNER, code3.RUNNER_BLOB), (code3.TEST, code3.TEST_BLOB))}
        tracked[code3.LIVE_IMPORTER] = {"sha": "0"*40}
        refs = {p: {"class": code3.classify(p)} for p in code3.REQUIRED_REFERENCES}
        code3.check_pre_retirement(tracked, refs)
        for key in (code3.SRC, code3.HDR, code3.RUNNER, code3.TEST):
            damaged = {k: dict(v) for k, v in tracked.items()}
            damaged[key]["sha"] = "f"*40
            with self.assertRaisesRegex(ValueError, "SOURCE_OR_CANDIDATE_BLOB_DRIFT"):
                code3.check_pre_retirement(damaged, refs)
            removed = dict(tracked)
            removed.pop(key)
            with self.assertRaisesRegex(ValueError, "SOURCE_OR_CANDIDATE_BLOB_DRIFT"):
                code3.check_pre_retirement(removed, refs)

    def test_missing_active_consumer_fails_closed(self):
        tracked = {p: {"sha": sha, "mode": "100644"} for p, sha in
                   ((code3.SRC, code3.SRC_BLOB), (code3.HDR, code3.HDR_BLOB),
                    (code3.RUNNER, code3.RUNNER_BLOB), (code3.TEST, code3.TEST_BLOB))}
        tracked[code3.LIVE_IMPORTER] = {"sha": "0"*40}
        refs = {p: {"class": code3.classify(p)} for p in code3.REQUIRED_REFERENCES}
        for key in code3.REQUIRED_REFERENCES:
            missing = dict(refs)
            missing.pop(key)
            with self.assertRaisesRegex(ValueError, "REQUIRED_LIVE_OR_GENERATED_CONSUMER_MISSING"):
                code3.check_pre_retirement(tracked, missing)


if __name__ == "__main__":
    unittest.main()
