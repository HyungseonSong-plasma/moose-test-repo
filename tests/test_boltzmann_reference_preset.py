"""BOLSIG+ manual examples are reference presets, not inferred Ar/O2 defaults."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from physics_app.ci.boltzmann_reference_preset import (
    OFFICIAL_PRESETS,
    ReferencePresetError,
    make_reference_preset,
)


def _source(root: Path) -> Path:
    source = root / "private_mixture_cross_sections.txt"
    # An original, nonphysical placeholder. No LXCat content is redistributed.
    source.write_bytes(b"ORIGINAL ARTIFICIAL INPUT ONLY\n")
    return source


def test_official_example4_default_is_four_gas_not_binary(tmp_path: Path) -> None:
    source = _source(tmp_path)
    out = tmp_path / "official_example4"
    manifest = make_reference_preset(source, out)
    assert manifest["preset"] == "official_example4"
    assert manifest["is_official_manual_example"]
    assert manifest["mixture"] == {
        "Ar": 0.7, "He": 0.2, "N2": 0.08, "O2": 0.02
    }
    assert sum(manifest["mixture"].values()) == pytest.approx(1.0)
    assert manifest["conditions"]["E_over_N_Td"] == 10.0
    assert manifest["conditions"]["gas_temperature_K"] == 300.0
    assert manifest["conditions"]["growth_model"] == "temporal"
    assert manifest["status"] == "REFERENCE_INPUT_ONLY_NOT_EXECUTED"
    script_path = out / manifest["script_file"]
    script = script_path.read_text(encoding="utf-8")
    assert "READCOLLISIONS\n" in script
    assert "\nAr  He  N2  O2\n" in script
    assert f"READCOLLISIONS\n{source.resolve()}" in script
    assert f"{source.resolve()}" in script
    assert hashlib.sha256(script_path.read_bytes()).hexdigest() == manifest["script_sha256"]
    assert manifest["collision_source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    saved = json.loads((out / "official_example4_manifest.json").read_text())
    assert saved["mixture"] == manifest["mixture"]
    with pytest.raises(ReferencePresetError, match="empty|overwrite"):
        make_reference_preset(source, out)


def test_official_example1_is_arn2_not_aro2(tmp_path: Path) -> None:
    assert OFFICIAL_PRESETS["official_example1"] == (
        ("Ar", 0.7), ("N2", 0.3)
    )
    out = tmp_path / "official_example1"
    manifest = make_reference_preset(
        _source(tmp_path), out, preset="official_example1"
    )
    assert manifest["mixture"] == {"Ar": 0.7, "N2": 0.3}
    assert "O2" not in manifest["mixture"]
    with pytest.raises(ReferencePresetError, match="immutable"):
        make_reference_preset(_source(tmp_path), tmp_path / "forced",
                              preset="official_example4", ar_fraction=0.7)


def test_binary_aro2_is_project_defined_and_requires_explicit_fraction(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    with pytest.raises(ReferencePresetError, match="explicit"):
        make_reference_preset(source, tmp_path / "missing",
                              preset="project_ar_o2_binary")
    manifest = make_reference_preset(
        source, tmp_path / "binary",
        preset="project_ar_o2_binary", ar_fraction=0.6,
    )
    assert manifest["mixture"] == {"Ar": 0.6, "O2": 0.4}
    assert manifest["is_official_manual_example"] is False
    assert manifest["status"] == "REFERENCE_INPUT_ONLY_NOT_EXECUTED"
    with pytest.raises(ReferencePresetError, match="explicit"):
        make_reference_preset(source, tmp_path / "bad",
                              preset="project_ar_o2_binary", ar_fraction=1.0)


def test_missing_or_unsafe_reference_source_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ReferencePresetError, match="does not exist"):
        make_reference_preset(tmp_path / "not_found.txt", tmp_path / "missing")
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"")
    with pytest.raises(ReferencePresetError, match="empty"):
        make_reference_preset(empty, tmp_path / "empty_out")
    invalid = tmp_path / "source with spaces.txt"
    invalid.write_bytes(b"not physical data\n")
    with pytest.raises(ReferencePresetError, match="safe|spaces"):
        make_reference_preset(invalid, tmp_path / "unsafe")
