from __future__ import annotations

from pathlib import Path

from qpx_harness.cli.app import COMMANDS, _LEGACY_TARGETS

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "qpx_harness"


def test_qpx_harness_root_has_only_package_entrypoint() -> None:
    direct_modules = sorted(
        path.name for path in HARNESS.glob("*.py") if path.name != "__init__.py"
    )
    assert direct_modules == []


def test_scale_analysis_remains_reusable_but_dedicated_campaign_cli_is_retired() -> None:
    analysis = HARNESS / "analysis" / "scale_audit.py"
    assert analysis.is_file()
    assert "scale-audit" not in COMMANDS
    assert "scale-audit" not in _LEGACY_TARGETS
    text = analysis.read_text()
    assert "Issue #43" not in text
    assert "QVT_SCALE" not in text
    assert "DEFAULT_PRESSURE" not in text


def test_evidence_diagnose_smoke_is_validation_owned() -> None:
    assert (HARNESS / "validation" / "evidence_diagnose_smoke.py").is_file()
    assert not (HARNESS / "evidence_diagnose_smoke.py").exists()


def test_stale_bundle_surface_is_retired() -> None:
    assert "bundle" not in COMMANDS
    assert "bundle" not in _LEGACY_TARGETS
    assert not (HARNESS / "bundle.py").exists()
