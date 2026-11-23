"""P0 tests for a pinned, archival-only FDEG Thermal Diffusion receipt."""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ci/guards"))
import fdeg_thermal_archive as archive  # noqa: E402
import fdeg_retirement_evidence as receipt_tool  # noqa: E402


class ThermalArchiveContractTest(unittest.TestCase):
    def make_bundle(self):
        head = "a" * 40
        source = {"src/thermal.C": "b" * 40}
        graph = {
            "structural": {"graph_id": "g:struct", "repository_head": head},
            "functional": {
                "graph_id": "g:functional",
                "source_identity": {
                    "repository_head": head,
                    "structural_graph_id": "g:struct",
                },
            },
            "transition": {
                "graph_id": "g:transition",
                "source_identity": {
                    "repository_head": head,
                    "structural_graph_id": "g:struct",
                    "functional_graph_id": "g:functional",
                },
                "safe_delete": "HOLD",
            },
        }
        manifest = {
            "schema": receipt_tool.SCHEMA,
            "lifecycle": "PRE_RETIREMENT",
            "target": "ThermalFixture",
            "baseline_head": head,
            "source_blobs": source,
            "graph_ids": {name: item["graph_id"] for name, item in graph.items()},
            "graph_sha256": {
                name: receipt_tool.sha256(receipt_tool.canonical(item))
                for name, item in graph.items()
            },
            "actual_caller_zero": "NOT_PROVEN",
            "actual_runtime_activation": "NOT_OBSERVED",
            "physics_parity": "NOT_PROVEN",
            "safe_delete": "HOLD",
        }
        manifest["manifest_sha256"] = receipt_tool.sha256(
            receipt_tool.canonical(manifest)
        )
        data = {"manifest.json": manifest}
        data.update({name + ".json": item for name, item in graph.items()})
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for name, item in sorted(data.items()):
                z.writestr(name, receipt_tool.canonical(item))
        blob = buf.getvalue()
        pin = {
            "schema": archive.SCHEMA,
            "target": "ThermalFixture",
            "baseline_head": head,
            "artifact_zip_sha256": hashlib.sha256(blob).hexdigest(),
            "manifest_sha256": manifest["manifest_sha256"],
            "source_blobs": source,
            "graph_sha256": manifest["graph_sha256"],
        }
        return blob, pin

    def test_clean_archive_verifies_without_live_source(self):
        blob, pin = self.make_bundle()
        result = archive.verify_archive_bytes(blob, pin)
        self.assertEqual(result["archive_integrity"], "PASS")
        self.assertFalse(result["global_consumer_closed"])
        self.assertFalse(result["safe_delete"])
        self.assertFalse(result["science_accepted"])

    def test_modified_zip_and_wrong_source_identity_fail_closed(self):
        blob, pin = self.make_bundle()
        with self.assertRaisesRegex(ValueError, "ZIP_SHA_MISMATCH"):
            archive.verify_archive_bytes(blob + b"x", pin)
        wrong = copy.deepcopy(pin)
        wrong["source_blobs"]["src/thermal.C"] = "c" * 40
        with self.assertRaisesRegex(ValueError, "PINNED_IDENTITY_MISMATCH"):
            archive.verify_archive_bytes(blob, wrong)

    def test_wrong_baseline_head_or_missing_graph_is_rejected(self):
        blob, pin = self.make_bundle()
        wrong = dict(pin, baseline_head="f" * 40)
        with self.assertRaisesRegex(ValueError, "PINNED_IDENTITY_MISMATCH"):
            archive.verify_archive_bytes(blob, wrong)
        wrong = dict(pin, artifact_zip_sha256=hashlib.sha256(b"oops").hexdigest())
        with self.assertRaisesRegex(ValueError, "ZIP_SHA_MISMATCH"):
            archive.verify_archive_bytes(blob, wrong)

    def test_pinned_real_archive_source_blobs_match_precut_checkout(self):
        pin = json.loads((
            ROOT / "reports/issue774/fdeg_thermal_historical_anchor_v0_1.json"
        ).read_text())
        self.assertEqual(pin["target"], "PhysicsFVThermalDiffusion")
        self.assertEqual(pin["workflow_artifact_id"], 14806741858)
        self.assertFalse(pin["safe_delete"])
        for path, blob_sha in pin["source_blobs"].items():
            raw = (ROOT / path).read_bytes()
            git_blob = hashlib.sha1(
                b"blob " + str(len(raw)).encode() + b"\x00" + raw
            ).hexdigest()
            self.assertEqual(git_blob, blob_sha)


    def test_reproduced_original_artifact_has_matching_immutable_graphs(self):
        pin = json.loads((
            ROOT / "reports/issue774/fdeg_thermal_historical_anchor_v0_1.json"
        ).read_text())
        archive_path = ROOT / "reports/issue774/archive/fdeg-retirement-code7-45148961276-1.zip"
        blob = archive_path.read_bytes()
        self.assertEqual(len(blob), 37949)
        self.assertEqual(hashlib.sha256(blob).hexdigest(), pin["artifact_zip_sha256"])
        result = archive.verify_archive_bytes(blob, pin)
        self.assertEqual(result["archive_integrity"], "PASS")
        self.assertEqual(result["target"], "PhysicsFVThermalDiffusion")
        self.assertEqual(result["baseline_head"], pin["baseline_head"])
        self.assertFalse(result["safe_delete"])
        self.assertFalse(result["global_consumer_closed"])
        self.assertFalse(result["science_accepted"])

    def test_archive_missing_graph_rejected_even_with_recomputed_zip_digest(self):
        blob, pin = self.make_bundle()
        src = zipfile.ZipFile(io.BytesIO(blob))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for name in src.namelist():
                if name != "transition.json":
                    out.writestr(name, src.read(name))
        damaged = buf.getvalue()
        matching_digest = dict(pin, artifact_zip_sha256=hashlib.sha256(damaged).hexdigest())
        with self.assertRaisesRegex(ValueError, "UNEXPECTED_ENTRIES"):
            archive.verify_archive_bytes(damaged, matching_digest)

if __name__ == "__main__":
    unittest.main()
