"""Synthetic-only Phelps 1978 O2 inventory tests; NO licensed source rows."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

FILE = (Path(__file__).resolve().parents[2] /
        "experiments/Issue395_powered_chemistry_ladder/collect_phelps_o2_core_set.py")
SPEC = importlib.util.spec_from_file_location("phelps_o2_core", FILE)
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m
SPEC.loader.exec_module(m)


def make_channel(ch):
    energy = [0.]
    anchor = ch.threshold_anchor if ch.threshold_anchor is not None else (
        ch.loss if ch.loss and ch.loss > 0 else .05
    )
    energy.append(float(anchor))
    energy += [anchor + .1 * (i - 1) for i in range(2, ch.count)]
    if ch.name == "rotation_300K":
        # An intentionally synthetic nonstrict knot, echoing the SOURCE hazard.
        energy[33] = energy[32]
    sigmas = [(.35 if ch.name == "momentum_effective" else 0.)]
    sigmas += [0.] + [i*.001 for i in range(2, ch.count)]
    marker = ("ENERGY Effective Qm - Defined in introduction"
              if ch.name == "momentum_effective" else
              "ENERGY CROSS SECTION ENERGY CROSS SECTION"
              if ch.name == "rotation_300K" else "ENERGY CROSS SECTION")
    meta = ("" if ch.name == "momentum_effective" else
            f"ENERGY LOSS = {ch.loss:.3f}, LOWER LIMIT = 0, UPPER LIMIT = 100,\n"
            f"QSCALE = {ch.qscale:.6f}\n")
    data = "\n".join(f"{i+1} {e:.6f} {s:.6f}" for i, (e, s)
                     in enumerate(zip(energy, sigmas)))
    return f"{ch.heading}\n{meta}{marker}\n{data}\n"


def synthetic():
    return "SYNTHETIC DATA - NOT ORIGINAL PHELPS\n" + "\n".join(
        make_channel(ch) for ch in m.CHANNELS
    )


def test_18_sections_individually_and_manifest(tmp_path):
    text = synthetic()
    assert len(m.CHANNELS) == 18
    for ch in m.CHANNELS:
        points, duplicates = m.extract(text, ch)
        assert len(points) == ch.count
        assert all(e >= 0 and sigma >= 0 for e, sigma in points)
        assert len(duplicates) == (1 if ch.name == "rotation_300K" else 0)
    input_path = tmp_path / "test_synthetic.txt"
    input_path.write_text(text, encoding="utf-8")
    output = tmp_path / "private" / "extracted"
    result = m.collect(input_path, output, "2026-10-30")
    assert result["status"] == "EXTRACTED_SOURCE_ONLY_NOT_BOLTZMANN_READY"
    assert len(result["channels"]) == 18
    assert result["channels"]["momentum_effective"]["use_as_elastic_momentum"] is False
    assert result["channels"]["rotation_300K"]["duplicate_knots"]
    assert result["channels"]["attachment_three_body"]["requires_density_normalization"]
    assert result["channels"]["v1_low"]["source_qscale"] == 2.5
    assert len(list(output.glob("*.csv"))) == 18
    assert (output / "phelps_o2_core_manifest.json").exists()
    with pytest.raises(FileExistsError, match="overwrite"):
        m.collect(input_path, output, "2026-10-30")


def test_changed_source_qscale_fails_closed():
    src = synthetic().replace("QSCALE = 2.500000", "QSCALE = 1.000000", 1)
    ch = next(c for c in m.CHANNELS if c.name == "v1_low")
    with pytest.raises(ValueError, match="QSCALE"):
        m.extract(src, ch)


def test_lost_section_fails_closed():
    src = synthetic().replace("O2 130 NM LINE MUMMA-ZIPF", "LOST SECTION")
    ch = next(c for c in m.CHANNELS if c.name == "line_130nm")
    with pytest.raises(ValueError, match="exact heading"):
        m.extract(src, ch)


def test_duplicate_knot_in_nonrotation_fails_closed():
    src = synthetic()
    ch = next(c for c in m.CHANNELS if c.name == "v2_low")
    original = make_channel(ch)
    replacement = original.replace(
        "3 0.480000", "3 0.380000", 1
    )
    assert original != replacement
    src = src.replace(original, replacement)
    with pytest.raises(ValueError, match="duplicate energy"):
        m.extract(src, ch)


def test_missing_rotation_duplicate_fails_review():
    src = synthetic()
    ch = next(c for c in m.CHANNELS if c.name == "rotation_300K")
    orig = make_channel(ch)
    # Supply strictly increasing synthetic energies, contrary to this original.
    src = src.replace(orig, orig.replace("34 3.250000", "34 3.350000"))
    with pytest.raises(ValueError, match="source duplicate knot disappeared"):
        m.extract(src, ch)
