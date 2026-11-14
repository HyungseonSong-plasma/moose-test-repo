"""Post-P3 evidence integrity: byte-based proof, no scientific acceptance."""
from pathlib import Path
import hashlib
import importlib.util
import json
import pytest

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "experiments/Issue402_plasma_dsl_g1"
spec = importlib.util.spec_from_file_location(
    "p3_chem_evidence_gate", PILOT / "verify_chemistry_p3_evidence.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_p3_evidence_requires_hashes_exact_head_and_no_science_claim(tmp_path):
    root = tmp_path / "results"
    root.mkdir()
    sha = "a" * 40
    data = {"plasma.e": b"exodus synthetic bytes", "plasma.csv": b"time,probe\n0,1\n"}
    for name, b in data.items():
        (root / name).write_bytes(b)
    hashes = {k: hashlib.sha256(v).hexdigest() for k, v in data.items()}
    common = {"case": "417", "arm": "D", "physics_mode": "chemistry",
              "source_sha": sha, "science": "SCIENCE_HOLD", "P3": "PASS"}
    manifest = dict(common, files={k: {"sha256": v} for k, v in hashes.items()})
    status = dict(common, P0="PASS", P1="PASS_SOURCE_BOUND_BINARY",
                  P2="PASS", P4="DIAGNOSTIC_ONLY",
                  status="PASS_P3_REFERENCE_DIAGNOSTIC",
                  binary_sha256="b", sidecar_sha256="c",
                  p2_log_sha256="d", p3_log_sha256="e",
                  native_exodus_sha256=hashes["plasma.e"],
                  native_csv_sha256=hashes["plasma.csv"],
                  canonical_fields={"frames": 461, "electron_energy": "log_e_energy"},
                  scratch_chemistry_cutover={"removed_count": 9})
    (root / "status.json").write_text(json.dumps(status))
    (root / "manifest.json").write_text(json.dumps(manifest))
    verdict = module.verify(root, sha, "417")
    assert verdict["artifact_rest_receipt"] == "PENDING"
    assert verdict["science"] == "SCIENCE_HOLD"
    (root / "plasma.csv").write_bytes(b"tamper")
    with pytest.raises(ValueError, match="P3_EVIDENCE_OUTPUT_SHA_MISMATCH"):
        module.verify(root, sha, "417")


def test_p3_evidence_rejects_wrong_case(tmp_path):
    with pytest.raises(ValueError, match="P3_EVIDENCE_INVALID_REQUEST"):
        module.verify(tmp_path, "short", "417")
