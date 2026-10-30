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
    sigmas = [(.35 if ch.name == "momentum_effective" else 0.)]
    sigmas += [0.] + [i*.001 for i in range(2, ch.count)]
    marker = ("ENERGY Effective Qm - Defined in introduction"
              if ch.name == "momentum_effective" else
              "ENERGY CROSS SECTION")
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


def test_14_selected_sections_and_manifest(tmp_path):
    text = synthetic()
    assert len(m.CHANNELS) == 14
    assert {ch.name for ch in m.CHANNELS}.isdisjoint(m.EXCLUDED_SOURCE_CHANNELS)
    assert "attachment_three_body" not in {ch.name for ch in m.CHANNELS}
    for ch in m.CHANNELS:
        points, duplicates = m.extract(text, ch)
        assert len(points) == ch.count
        assert all(e >= 0 and sigma >= 0 for e, sigma in points)
        assert not duplicates
    input_path = tmp_path / "test_synthetic.txt"
    input_path.write_text(text, encoding="utf-8")
    output = tmp_path / "private" / "extracted"
    result = m.collect(input_path, output, "2026-10-30")
    assert result["status"] == "EXTRACTED_SOURCE_ONLY_NOT_BOLTZMANN_READY"
    assert len(result["channels"]) == 14
    assert result["excluded_source_channels"] == sorted(m.EXCLUDED_SOURCE_CHANNELS)
    assert result["excluded_unregistered_source_channels"] == ["attachment_three_body"]
    assert result["channels"]["momentum_effective"]["use_as_elastic_momentum"] is False
    assert "attachment_three_body" not in result["channels"]
    assert result["channels"]["v1_low"]["source_qscale"] == 2.5
    assert len(list(output.glob("*.csv"))) == 14
    assert not list(output.glob("*rotation*"))
    assert not list(output.glob("*b1sigma*"))
    assert not list(output.glob("*130nm*"))
    assert not list(output.glob("*three_body*"))
    assert (output / "phelps_o2_core_manifest.json").exists()
    with pytest.raises(FileExistsError, match="overwrite"):
        m.collect(input_path, output, "2026-10-30")


def test_changed_source_qscale_fails_closed():
    src = synthetic().replace("QSCALE = 2.500000", "QSCALE = 1.000000", 1)
    ch = next(c for c in m.CHANNELS if c.name == "v1_low")
    with pytest.raises(ValueError, match="QSCALE"):
        m.extract(src, ch)


def test_lost_section_fails_closed():
    src = synthetic().replace("O2 IONIZATION", "LOST SECTION")
    ch = next(c for c in m.CHANNELS if c.name == "ionization")
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


def test_excluded_low_priority_collisions_not_selected():
    names = {c.name for c in m.CHANNELS}
    assert not names & {"rotation_300K", "b1sigma", "line_130nm"}
    assert m.EXCLUDED_SOURCE_CHANNELS == frozenset(
        {"attachment_three_body", "rotation_300K", "b1sigma", "line_130nm"}
    )

def test_unregistered_three_body_not_generated(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text(
        synthetic()
        + "\nO2 THREE-BODY ATTACHMENT\n"
        + "ENERGY LOSS = 0\nQSCALE = 1\nENERGY CROSS SECTION\n"
        + "1 0 0\n2 1 0.1\n",
        encoding="utf-8",
    )
    output = tmp_path / "converted"
    manifest = m.collect(source, output, "2026-10-30")
    assert len(manifest["channels"]) == 14
    assert "attachment_three_body" not in manifest["channels"]
    assert not list(output.glob("*three_body*"))


def test_registering_unapproved_attachment_is_rejected(monkeypatch, tmp_path):
    channel = m.Channel(
        "attachment_three_body", "O2 THREE-BODY ATTACHMENT",
        36, 0., 1., "DENSITY_NORMALIZED_THREE_BODY"
    )
    monkeypatch.setattr(m, "CHANNELS", m.CHANNELS + (channel,))
    source = tmp_path / "input.txt"
    source.write_text(synthetic(), encoding="utf-8")
    with pytest.raises(ValueError, match="OUT_OF_SCOPE_COLLISION"):
        m.collect(source, tmp_path / "out", "2026-10-30")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("key", ["rotation_300K", "b1sigma", "line_130nm"])
def test_reinsertion_of_excluded_source_fails_closed(monkeypatch, tmp_path, key):
    ch = m.Channel(key, "EXCLUDED TEST", 2, 0., 1., "EXCLUDED")
    monkeypatch.setattr(m, "CHANNELS", m.CHANNELS + (ch,))
    original = tmp_path / "source.txt"
    original.write_text(synthetic(), encoding="utf-8")
    with pytest.raises(ValueError, match="OUT_OF_SCOPE_COLLISION"):
        m.collect(original, tmp_path / "out", "2026-10-30")
    assert not (tmp_path / "out").exists()
