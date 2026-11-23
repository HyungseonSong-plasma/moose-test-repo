"""D6 exact-HEAD Git witness and fail-closed scope regression tests."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
from issue774_d6_consumer_scope import (  # noqa: E402
    SOURCE, TARGET, audit, classify,
)


class D6ConsumerWitnessTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Issue774 CI")
        self.git("config", "user.email", "ci@example.invalid")

    def git(self, *args):
        r = subprocess.run(["git", "-C", str(self.root), *args],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return r.stdout.decode().strip()

    def put(self, path, text):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
        return file

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "synthetic D6 facts")
        return self.git("rev-parse", "HEAD")

    def test_full_tree_token_witness_and_qpx_are_separate(self):
        self.put("experiments/old/input.i", "type = PhysicsFVThermalDiffusion\n")
        self.put("experiments/new/generate.py",
                 "KERNEL = 'PhysicsFVThermalDiffusion'\n")
        self.put("reports/issue774/a.json", '{"target":"PhysicsFVThermalDiffusion"}\n')
        self.put("tests/test_fdeg_contract.py", 'NAME="PhysicsFVThermalDiffusion"\n')
        self.put("experiments/qpx/input.i", "type = QPXFVThermalDiffusion\n")
        head = self.commit()
        result = audit(self.root, head)
        rows = {r["path"]: r for r in result["reference_paths"]}
        self.assertEqual(result["source_head"], head)
        self.assertEqual(result["tracked_path_count"], 5)
        self.assertTrue(result["source_and_header_absent"])
        self.assertEqual(rows["experiments/old/input.i"]["reference_class"],
                         "MOOSE_INPUT_CONSUMER_REVIEW")
        self.assertEqual(rows["experiments/new/generate.py"]["reference_class"],
                         "GENERATOR_OR_SCRIPT_REFERENCE_REVIEW")
        self.assertEqual(rows["reports/issue774/a.json"]["reference_class"],
                         "DOCUMENTED_EVIDENCE_REVIEW")
        self.assertEqual(rows["experiments/qpx/input.i"]["reference_class"],
                         "DISTINCT_QPX_APP_KEEP_UNCHANGED")
        self.assertFalse(result["safe_to_delete"])
        self.assertEqual(result["independent_external_consumer_scope"],
                         "NOT_ATTESTED")
        self.assertTrue(all("git_blob_sha1" in row for row in rows.values()))

    def test_source_present_is_not_a_retirement_pass(self):
        self.put(SOURCE, 'registerMooseObject("PhysicsApp", PhysicsFVThermalDiffusion);\n')
        head = self.commit()
        result = audit(self.root, head)
        self.assertFalse(result["source_and_header_absent"])
        self.assertIn("RETIRED_SOURCE_REINTRODUCED",
                      result["reference_class_counts"])

    def test_git_commit_bytes_not_changed_worktree_are_audited(self):
        file = self.put("cases/current.i", "type = PhysicsFVThermalDiffusion\n")
        head = self.commit()
        file.write_text("type = AnotherKernel\n")
        result = audit(self.root, head)
        self.assertEqual(result["reference_paths"][0]["target_line_numbers"], [1])
        self.assertEqual(result["source_head"], head)
        with self.assertRaisesRegex(ValueError, "D6_EXACT_HEAD_MISMATCH"):
            audit(self.root, "f" * 40)

    def test_active_profile_and_workflow_are_not_archives(self):
        self.put("ci/baselines/fdeg_functional_contracts.json",
                 '{"profiles":{"PhysicsFVThermalDiffusion":{}}}\n')
        self.put(".github/workflows/physics-code-ci.yml",
                 "run: echo PhysicsFVThermalDiffusion\n")
        head = self.commit()
        rows = {r["path"]: r for r in audit(self.root, head)["reference_paths"]}
        self.assertEqual(rows["ci/baselines/fdeg_functional_contracts.json"][
            "reference_class"], "ACTIVE_FDEG_PROFILE_REVIEW")
        self.assertEqual(rows[".github/workflows/physics-code-ci.yml"][
            "reference_class"], "LIVE_WORKFLOW_DEPENDENCY_REVIEW")

    def test_classification_never_grants_compatibility(self):
        self.assertEqual(classify("archive/old.i", has_target=True,
                                  has_other_app=False, direct_type=True,
                                  active_profile=False), "MOOSE_INPUT_CONSUMER_REVIEW")
        self.assertEqual(classify("docs/a.md", has_target=True,
                                  has_other_app=False, direct_type=False,
                                  active_profile=False), "DOCUMENTED_EVIDENCE_REVIEW")
        self.assertEqual(TARGET, "PhysicsFVThermalDiffusion")


if __name__ == "__main__":
    unittest.main()
