"""Synthetic parser tests; original copyrighted Phelps point pairs are not embedded."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

MODULE_FILE = (
    Path(__file__).resolve().parents[2]
    / "experiments/Issue395_powered_chemistry_ladder/collect_phelps_o2_4p5.py"
)
spec = importlib.util.spec_from_file_location("collect_phelps_o2_4p5", MODULE_FILE)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def synthetic_source() -> str:
    energies = [0, 4.5, 4.8, 5, 5.5, 6, 6.5, 7, 7.5, 8, 9, 10, 12, 15, 50, 10000]
    # Deliberately synthetic: these are NOT Phelps cross-section values.
    values = [0.0 if i < 2 or i >= 13 else i * 0.0007 for i in range(16)]
    rows = "\n".join(
        f" {i + 1} {e:.4f} {v:.4f}" for i, (e, v) in enumerate(zip(energies, values))
    )
    return (
        "COMPILATION OF ELECTRON CROSS SECTIONS USED BY A. V. PHELPS\n"
        "The cross sections are in 1E-16 cm2.\n"
        "O2 4.5 LOSS\n"
        "ENERGY LOSS = 4.500 , LOWER LIMIT = 4.386 , UPPER LIMIT = 14.990 ,\n"
        "QSCALE = 1.000000\nENERGY CROSS SECTION\n"
        + rows + "\nO2 6.0 LOSS\nENERGY LOSS = 6.000\n"
    )


def test_4p5_parser_bounds_and_units() -> None:
    rows = m.parse_o2_4p5_source(synthetic_source())
    assert len(rows) == 16
    assert rows[1] == (4.5, 0.0)
    assert rows[2][0] == 4.8
    assert rows[2][1] == pytest.approx(0.0014e-20)
    assert rows[-3:] == [(15.0, 0.0), (50.0, 0.0), (10000.0, 0.0)]


@pytest.mark.parametrize("corrupt", [
    lambda s: s.replace("O2 4.5 LOSS", "O2 5.0 LOSS"),
    lambda s: s.replace("QSCALE = 1.000000", "QSCALE = 0.500000"),
    lambda s: s.replace("ENERGY LOSS = 4.500", "ENERGY LOSS = 6.000"),
    lambda s: s.replace("O2 6.0 LOSS", "O2 6.1 LOSS"),
    lambda s: s.replace(" 16 10000.0000 0.0000", ""),
    lambda s: s + s[s.index("O2 4.5 LOSS"):],
])
def test_wrong_channel_fails_closed(corrupt) -> None:
    with pytest.raises(ValueError):
        m.parse_o2_4p5_source(corrupt(synthetic_source()))


def test_local_provenance_hash_and_no_overwrite(tmp_path) -> None:
    source = tmp_path / "phelps_source.txt"
    source.write_text(synthetic_source(), encoding="utf-8")
    local = tmp_path / "local_cross_sections"
    meta = m.convert(source, local, "2026-10-30")
    assert meta["reaction_id"] == 411
    assert meta["source_section"] == "O2 4.5 LOSS"
    assert meta["point_count"] == 16
    assert meta["energy_loss_eV"] == 4.5
    assert meta["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert (local / m.OUTPUT_CSV).is_file()
    assert (local / m.OUTPUT_MANIFEST).is_file()
    with pytest.raises(FileExistsError):
        m.convert(source, local, "2026-10-30")
    assert m.convert(source, local, "2026-10-30", replace=True) == meta
