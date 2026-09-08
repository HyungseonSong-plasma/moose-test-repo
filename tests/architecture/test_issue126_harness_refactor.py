from pathlib import Path

from qpx_harness.evidence import normalize_face_evidence

ROOT = Path(__file__).resolve().parents[2]


def test_protocol_registry_is_physically_retired_from_canonical_application():
    application = ROOT / "qpx_harness" / "application"
    assert not (application / "experiment_registry.py").exists()
    assert not (application / "experiment_service.py").exists()
    assert not (application / "protocols").exists()


def test_evidence_public_api_no_longer_exports_analysis_facades():
    import qpx_harness.evidence as evidence

    assert normalize_face_evidence is evidence.normalize_face_evidence
    assert not hasattr(evidence, "prepare_face_evidence")
    assert not hasattr(evidence, "build_cell_evidence")
    assert not hasattr(evidence, "write_evidence_bundle")


def test_dependency_guard_has_no_evidence_analysis_exception():
    text = (ROOT / "tools" / "qpx_dependency_guard.py").read_text()
    assert "qpx_harness.evidence.transform\", \"qpx_harness.analysis.green_gauss" not in text
