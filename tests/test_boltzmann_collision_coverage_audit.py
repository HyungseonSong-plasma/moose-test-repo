"""S2 synthetic four-gas science preflight; no third-party collision data."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from physics_app.ci.boltzmann_collision_coverage_audit import (
    CollisionAuditError,
    audit_local_collision_file,
)


def _elastic(gas: str) -> str:
    return (
        f"ELASTIC\n{gas}\n1.37e-5\n"
        "synthetic original author, NOT LXCat\n------\n"
        "0 5e-20\n10 5e-20\n------\n"
    )


def _source(directory: Path, text: str) -> Path:
    file = directory / "local_fourgas_synthetic.txt"
    file.write_text(text, encoding="utf-8")
    return file


def test_official_example4_species_structure_is_not_physical_parity(tmp_path: Path) -> None:
    source = _source(tmp_path, (
        "SYNTHETIC EXAMPLE4 SPECIES NAMES ONLY\n" +
        "".join(_elastic(gas) for gas in ("Ar", "He", "N2", "O2")) +
        "EXCITATION\nN2 -> N2_test\n0.3\n"
        "synthetic\n------\n0 0\n0.3 0\n10 2e-20\n------\n"
        "IONIZATION\nAr -> Ar_plus\n0.8\n"
        "synthetic\n------\n0 0\n0.8 0\n10 2e-20\n------\n"
        "ATTACHMENT\nO2 -> O2_minus\n"
        "synthetic\n------\n0 1e-20\n10 1e-20\n------\n"
    ))
    result = audit_local_collision_file(source, required_energy_eV=10)
    assert result["status"] == "STRUCTURALLY_SUPPORTED_NOT_BOLSIG_VALIDATED"
    assert result["total_processes"] == 7
    assert result["process_counts"]["Ar"] == {"ELASTIC": 1, "IONIZATION": 1}
    assert result["process_counts"]["O2"] == {"ATTACHMENT": 1, "ELASTIC": 1}
    assert result["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["model_gaps"] == []


def test_effective_rotation_and_power_law_fail_closed(tmp_path: Path) -> None:
    fixture = "".join(_elastic(gas) for gas in ("Ar", "He", "N2", "O2"))
    fixture += (
        "EFFECTIVE\nO2\n3.4e-5\nsynthetic\n------\n"
        "0 2e-20\n10 2e-20\n------\n"
        "ROTATION\nN2\n0.03\nsynthetic\n------\n"
        "0 2e-20\n10 2e-20\n------\n"
        "EXCITATION\nAr -> Ar_test\n0.4\n"
        "synthetic formula\n------\n1.0 2e-20\n------\n"
    )
    source = _source(tmp_path, fixture)
    result = audit_local_collision_file(source)
    assert result["status"] == "PHYSICS_MODEL_HOLD"
    assert "DUPLICATE_MOMENTUM_PROVIDER:O2" in result["model_gaps"]
    assert any(x.startswith("ROTATION_UNSUPPORTED:") for x in result["model_gaps"])
    assert any(x.startswith("POWER_LAW_UNSUPPORTED:") for x in result["model_gaps"])
    assert result["total_processes"] == 7


def test_missing_species_and_coverage_gaps_trigger_science_hold(tmp_path: Path) -> None:
    source = _source(tmp_path, _elastic("Ar") + _elastic("O2"))
    result = audit_local_collision_file(source, required_energy_eV=12)
    assert result["status"] == "PHYSICS_MODEL_HOLD"
    assert "MISSING_SPECIES:He" in result["model_gaps"]
    assert "MISSING_ELASTIC_MOMENTUM:N2" in result["model_gaps"]
    assert any(x.startswith("CROSS_SECTION_COVERAGE_GAP:")
               for x in result["model_gaps"])


def test_malformed_cross_sections_cannot_be_classified_compatible(tmp_path: Path) -> None:
    with pytest.raises(CollisionAuditError, match="nonascending"):
        audit_local_collision_file(_source(
            tmp_path, _elastic("Ar").replace("10 5e-20", "0 5e-20")))
    with pytest.raises(CollisionAuditError, match="negative"):
        audit_local_collision_file(_source(
            tmp_path, _elastic("Ar").replace("10 5e-20", "10 -5e-20")))
    with pytest.raises(CollisionAuditError, match="no collision processes"):
        audit_local_collision_file(_source(tmp_path, "empty nonphysical text"))


def test_effective_momentum_excitation_only_is_structurally_supported(tmp_path: Path) -> None:
    # This reflects S7's bounded steady collision projector; it does not
    # establish real Ar/N2 source provenance or BOLSIG+ EEPF agreement.
    source = _source(tmp_path, (
        "SYNTHETIC EFFECTIVE WITH NO GROWTH REACTIONS\n" +
        "EFFECTIVE\nAr\n1.37e-5\nsource: invented\n------\n"
        "0 7e-20\n10 7e-20\n------\n" +
        "".join(_elastic(gas) for gas in ("He", "N2", "O2")) +
        "EXCITATION\nAr -> test_level\n0.5\nsource: invented\n------\n"
        "0 0\n0.5 0\n10 1e-20\n------\n"
    ))
    report = audit_local_collision_file(source, required_energy_eV=10)
    assert report["status"] == "STRUCTURALLY_SUPPORTED_NOT_BOLSIG_VALIDATED"
    assert not report["model_gaps"]

    # Adding even one particle-changing channel makes the EFFECTIVE
    # reconstruction an unsupported full-physics coupling, not PASS.
    added = source.read_text() + (
        "IONIZATION\nAr -> Ar+\n1\nsource: invented\n------\n"
        "0 0\n10 1e-20\n------\n"
    )
    source.write_text(added)
    held = audit_local_collision_file(source, required_energy_eV=10)
    assert held["status"] == "PHYSICS_MODEL_HOLD"
    assert "EFFECTIVE_GROWTH_COUPLING_UNSUPPORTED:Ar" in held["model_gaps"]


def test_duplicate_provider_and_threshold_outside_grid_hold(tmp_path: Path) -> None:
    source = _source(tmp_path, (
        "".join(_elastic(gas) for gas in ("Ar", "He", "N2", "O2")) +
        "EFFECTIVE\nAr\n1.37e-5\ninvented\n------\n"
        "0 8e-20\n10 8e-20\n------\n"
        "EXCITATION\nN2 -> v1\n12\ninvented\n------\n"
        "0 0\n10 0\n------\n"
    ))
    report = audit_local_collision_file(source, required_energy_eV=10)
    assert "DUPLICATE_MOMENTUM_PROVIDER:Ar" in report["model_gaps"]
    assert any(gap.startswith("INELASTIC_THRESHOLD_OUTSIDE_GRID:")
               for gap in report["model_gaps"])
    assert report["status"] == "PHYSICS_MODEL_HOLD"
