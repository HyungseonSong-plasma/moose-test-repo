from pathlib import Path

from qpx_harness.application.experiment_registry import registered_protocols
from qpx_harness.evidence import normalize_face_evidence

ROOT = Path(__file__).resolve().parents[2]


def test_current_registry_census_covers_all_declarative_protocols():
    protocols = set(registered_protocols())
    assert {
        "issue26-electron-energy-e1",
        "issue26-electron-energy-e2a",
        "issue26-electron-energy-chain",
        "issue27-surface-reaction-controlled-wall",
        "r3-electron-master-diagnostic",
        "r3-electron-scaling-counterfactual",
        "r3-fv-internal-completion",
        "r4-qf2-local-charge-relaxation",
    } <= protocols


def test_evidence_public_api_no_longer_exports_analysis_facades():
    import qpx_harness.evidence as evidence

    assert normalize_face_evidence is evidence.normalize_face_evidence
    assert not hasattr(evidence, "prepare_face_evidence")
    assert not hasattr(evidence, "build_cell_evidence")
    assert not hasattr(evidence, "write_evidence_bundle")


def test_dependency_guard_has_no_evidence_analysis_exception():
    text = (ROOT / "tools" / "qpx_dependency_guard.py").read_text()
    assert "qpx_harness.evidence.transform\", \"qpx_harness.analysis.green_gauss" not in text
