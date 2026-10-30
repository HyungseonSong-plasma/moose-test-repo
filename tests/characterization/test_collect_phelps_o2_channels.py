"""Synthetic-only Phelps channel parser tests. Not original cross-section data."""
from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path

import pytest

MODULE = (Path(__file__).resolve().parents[2] /
          "experiments/Issue395_powered_chemistry_ladder/collect_phelps_o2_channels.py")
spec = importlib.util.spec_from_file_location("phelps_channels", MODULE)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
# dataclasses consult sys.modules under Python 3.12 and 3.13.
import sys
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def synthetic_section(section) -> str:
    energies = [float(i * 0.7 + 1) for i in range(section.n)]
    energies[0] = 0.
    if section.threshold_eV is not None:
        energies[1] = section.threshold_eV
        energies[2:] = [section.threshold_eV + (i-1) * 5.0 for i in range(2, section.n)]
    else:
        energies[1:] = [float(i * 10) for i in range(1, section.n)]
    # Synthetic numeric values; not a copy of any Phelps source pair.
    sigmas = [0. if i <= 1 else i*0.003 + 0.01 for i in range(section.n)]
    if section.source_kind == "indexed":
        rows = [f"{i+1} {e:g} {q:g}" for i, (e, q) in
                enumerate(zip(energies, sigmas))]
        metadata = (f"ENERGY LOSS = {section.loss_eV:.3f} , "
                    "LOWER LIMIT = 1.00 , UPPER LIMIT = 100.001 ,\n"
                    f"QSCALE = {section.qscale:.6f}\n")
    else:
        rows = [f"{e:g} {q:g}" for e, q in zip(energies, sigmas)]
        metadata = "P. C. Cosby, J. Chem. Phys. 98, 9560 (1993).\n"
    # Each channel is deliberately independently synthetic.
    return (section.heading + "\n" + metadata + "ENERGY CROSS SECTION\n" +
            "\n".join(rows[:4]) + "\nPage 7 of 53\n" + "\n".join(rows[4:]) +
            "\nEND OF SYNTHETIC SECTION\n")


def source_text() -> str:
    return "PHELPS SYNTHETIC TEST FIXTURE\n" + "\n".join(
        synthetic_section(s) for s in m.SECTIONS
    )


def test_full_six_channels_extracted_without_cross_talk(tmp_path) -> None:
    s = source_text()
    for spec in m.SECTIONS:
        vals = m.section_data(s, spec)
        assert len(vals) == spec.n
        assert vals[0] == (0., 0.)
        assert vals[-1][1] > 0
        if spec.id == "401":
            assert spec.qscale == 1.2
        if spec.id == "412_dissociation":
            assert spec.source_kind == "unindexed"
            assert vals[1][0] == 10.0
    original = tmp_path / "original.txt"
    original.write_text(s)
    output_dir = tmp_path / "local" / "phelps"
    meta = m.collect(original, output_dir, "2026-10-30")
    assert meta["source_sha256"] == hashlib.sha256(original.read_bytes()).hexdigest()
    assert set(meta["channels"]) == {
        "401", "407", "411", "412_loss", "412_dissociation", "413"
    }
    assert meta["channels"]["411"]["species_source_accepted"] is False
    assert meta["channels"]["412_loss"]["species_source_accepted"] is False
    assert meta["channels"]["412_dissociation"]["species_source_accepted"] is True
    for spec in m.SECTIONS:
        channel = meta["channels"][spec.id]
        assert channel["sample_count"] == spec.n
        assert (output_dir/channel["path"]).exists()
    assert (output_dir/"phelps_o2_channels_provenance.json").exists()
    with pytest.raises(FileExistsError):
        m.collect(original, output_dir, "2026-10-30")


@pytest.mark.parametrize("section_id,broken", [
    ("401", "QSCALE = 1.200000"),
    ("407", "ENERGY LOSS = 0.977"),
    ("411", "O2 4.5 LOSS"),
    ("412_loss", "O2 6.0 LOSS"),
    ("412_dissociation", "P. C. Cosby"),
    ("413", "O2 8.4 LOSS HAYASHI ABOVE 20EV - CHANTRY BELOW"),
])
def test_source_mutations_detected(section_id, broken) -> None:
    source = source_text()
    spec = next(s for s in m.SECTIONS if s.id == section_id)
    source = source.replace(broken, "MUTATED SOURCE DATA", 1)
    with pytest.raises(ValueError):
        m.section_data(source, spec)


def test_guards_do_not_allow_spoofed_411_as_dissociation() -> None:
    spec = next(s for s in m.SECTIONS if s.id == "411")
    assert "not_validated" in spec.species_mapping
    assert "O2 4.5 LOSS" == spec.heading
    assert "DISSOCIATION" not in spec.heading
    diss = next(s for s in m.SECTIONS if s.id == "412_dissociation")
    assert diss.source_kind == "unindexed"
    assert diss.loss_eV is None
