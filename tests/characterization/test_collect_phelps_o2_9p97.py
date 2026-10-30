"""Synthetic 414 parser tests; no Phelps cross-section numeric data committed."""
from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path
import pytest

MODULE_FILE = (Path(__file__).resolve().parents[2] /
    "experiments/Issue395_powered_chemistry_ladder/collect_phelps_o2_9p97.py")
spec = importlib.util.spec_from_file_location("collect_phelps_o2_9p97", MODULE_FILE)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def synthetic_source():
    energies = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110,
                120, 140, 160, 200, 300, 1000, 1500, 2000, 3000, 5000, 7000, 10000]
    values = [0.0 if i < 2 or i >= 18 else .001*i for i in range(24)]
    rows = "\n".join(f" {i+1} {e:.4f} {s:.4f}" for i,(e,s) in enumerate(zip(energies,values)))
    return ("COMPILATION OF ELECTRON CROSS SECTIONS USED BY A. V. PHELPS\n"
        "The cross sections are in 1E-16 cm2.\n"
        "O2 9.97 LOSS TRAJMAR\n"
        "ENERGY LOSS = 10.000 , LOWER LIMIT = 9.778 , UPPER LIMIT = 100.001 ,\n"
        "QSCALE = 1.000000\nENERGY CROSS SECTION\n"+rows+
        "\nO2 IONIZATION\nENERGY LOSS = 12.060\n")

def test_414_parser_bounds_units():
    p = m.parse_o2_9p97_source(synthetic_source())
    assert len(p) == 24 and p[:2] == [(0.0, 0.0), (10.0, 0.0)]
    assert p[2][1] == pytest.approx(.002e-20)
    assert p[-6:] == [(e,0.0) for e in (1500,2000,3000,5000,7000,10000)]

@pytest.mark.parametrize("corrupt", [
    lambda s:s.replace("O2 9.97 LOSS TRAJMAR","O2 10.00 LOSS"),
    lambda s:s.replace("ENERGY LOSS = 10.000","ENERGY LOSS = 9.970"),
    lambda s:s.replace("QSCALE = 1.000000","QSCALE = 0.8"),
    lambda s:s.replace("LOWER LIMIT = 9.778","LOWER LIMIT = 9.000"),
    lambda s:s.replace("O2 IONIZATION","O2 IONISATION"),
    lambda s:s.replace(" 24 10000.0000 0.0000",""),
    lambda s:s+s[s.index("O2 9.97 LOSS TRAJMAR"):],
    lambda s:s.replace(" 3 20.0000 0.0020"," 3 20.0000 -0.0020"),
])
def test_malformed_source_fails_closed(corrupt):
    with pytest.raises(ValueError):
        m.parse_o2_9p97_source(corrupt(synthetic_source()))

def test_local_hash_provenance_and_no_implicit_overwrite(tmp_path):
    src=tmp_path/"source.txt"
    src.write_text(synthetic_source(),encoding="utf-8")
    out=tmp_path/"local"
    meta=m.convert(src,out,"2026-10-30")
    assert (meta["reaction_id"],meta["source_channel_label_eV"],meta["energy_loss_eV"],meta["point_count"]) == (414,9.97,10.0,24)
    assert meta["source_sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
    assert (out/m.OUTPUT_CSV).is_file() and (out/m.OUTPUT_MANIFEST).is_file()
    with pytest.raises(FileExistsError):
        m.convert(src,out,"2026-10-30")
    assert m.convert(src,out,"2026-10-30",replace=True) == meta
