"""Synthetic-only QA for O2(a1Delta_g) reactions 2072/2073/2074.

No copyrighted primary-source numeric cross sections are included.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

PATH = (Path(__file__).resolve().parents[2] /
        "experiments/Issue395_powered_chemistry_ladder/prepare_o2s_eimpact_2072_2074.py")
spec = importlib.util.spec_from_file_location("prepare_o2s_2072_2074", PATH)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def source_csv() -> str:
    # Invented synthetic only; no numeric values from Phelps, Cosby or 1992 measurements.
    return ("electron_energy_eV,cross_section_m2\n"
            "0,0\n"
            "10,0\n"
            "12,0\n"
            "13,1e-21\n"
            "14,2e-21\n"
            "20,2.5e-21\n"
            "30,3e-21\n"
            "40,3.5e-21\n"
            "50,3e-21\n")


def parent_source(tmp_path: Path, rid: int) -> tuple[Path, Path]:
    spec = m.REACTIONS[rid]
    fn = tmp_path / "original_data.csv"
    fn.write_text(source_csv(), encoding="utf-8")
    h = hashlib.sha256(fn.read_bytes()).hexdigest()
    if rid in (2072, 2073):
        heading = ("O2 IONIZATION" if rid == 2072 else
                   "O2 DISSOCIATION - BASED ON TABLE I OF")
        manifest = {
            "source": "A. V. Phelps O2 compilation",
            "source_url": "https://us.lxcat.net/notes/index.php?download=phelps5",
            "source_sha256": "a"*64,
            "channels": {
                spec.parent_channel: {
                    "reaction_id": spec.parent_id,
                    "path": fn.name,
                    "sha256": h,
                    "original_heading": heading,
                    "species_source_accepted": True,
                }
            }
        }
    else:
        manifest = {
            "reaction_id": 417,
            "parent_channel": "Oplus_fragment_partial",
            "original_target_state": "O2(X3Sigma_g-,v=0)",
            "original_source_doi": "10.1016/0168-1176(92)87037-F",
            "original_source_sha256": "b"*64,
            "csv_sha256": h,
        }
    manifest_path = tmp_path / "source_manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return fn, manifest_path


@pytest.mark.parametrize("rid", [2072, 2073, 2074])
def test_provenance_protected_shifted_cross_sections(tmp_path, rid) -> None:
    parent, manifest = parent_source(tmp_path, rid)
    dest = tmp_path / "derived"
    with pytest.raises(ValueError, match="accept-model-threshold-shift"):
        m.build(rid, parent, manifest, dest, "2026-10-30")
    out = m.build(rid, parent, manifest, dest, "2026-10-30", accept_model=True)
    assert out["reaction_id"] == rid
    assert out["target_state"] == "O2(a1Delta_g)"
    assert out["shift_eV"] == pytest.approx(.977)
    assert out["discarded_zero_source_rows"] == 1
    assert out["model_electron_loss_eV_PROVISIONAL"] == pytest.approx(
        {2072:11.083, 2073:5.023, 2074:19.023}[rid])
    assert out["validation_status"] == "DERIVED_MODEL_ONLY_NOT_EXPERIMENTAL_O2STAR_CROSS_SECTION"
    assert not out["boltzmann_rate_computed"]
    path = dest / out["output_file"]
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    assert rows[0]["electron_energy_eV"] == pytest.approx("9.023") if False else True
    assert float(rows[0]["electron_energy_eV"]) == pytest.approx(9.023)
    assert float(rows[2]["cross_section_m2"]) == pytest.approx(0.)
    assert float(rows[3]["cross_section_m2"]) == pytest.approx(1e-21)
    assert len(rows) == 8
    with pytest.raises(FileExistsError):
        m.build(rid, parent, manifest, dest, "2026-10-30", accept_model=True)
    assert m.build(rid, parent, manifest, dest, "2026-10-30",
                   accept_model=True, replace=True) == out


def test_nonmatching_parent_source_rejected(tmp_path) -> None:
    for rid in (2072, 2073, 2074):
        folder = tmp_path / str(rid)
        folder.mkdir()
        parent, manifest = parent_source(folder, rid)
        data = json.loads(manifest.read_text())
        if rid == 2072:
            data["channels"]["415"]["original_heading"] = "O2 DISSOCIATION"
        elif rid == 2073:
            data["channels"]["412_dissociation"]["species_source_accepted"] = False
        else:
            data["parent_channel"] = "O2plus_parent_total"
        manifest.write_text(json.dumps(data))
        with pytest.raises(ValueError):
            m.build(rid, parent, manifest, folder / "derived",
                    "2026-10-30", accept_model=True)


def test_reject_unphysical_sigma_and_invalid_source_state() -> None:
    for broken in (source_csv().replace("13,1e-21", "13,-1e-21"),
                   source_csv().replace("13,1e-21", "13,nan"),
                   source_csv().replace("20,2.5e-21", "20,inf"),
                   source_csv().replace("20,2.5e-21", "13,2.5e-21"),
                   source_csv().replace("13,1e-21", "0.5,1e-21"),
                   source_csv().replace("electron_energy_eV", "Te_eV")):
        with pytest.raises(ValueError):
            m.threshold_reduce(m.parse_ground_sigma(broken))


def test_reference_benchmarks_are_comparison_only() -> None:
    assert set(m.REACTIONS) == {2072, 2073, 2074}
    k2072, status = m.benchmark(2072, 3.0)
    assert status == "Kim2006_Table2.1"
    assert k2072 == pytest.approx(2.34e-15*3**1.03*__import__("math").exp(-11.31/3))
    k2073, status = m.benchmark(2073, 3.0)
    assert status == "Kim2006_Table2.1"
    assert k2073 == pytest.approx(6.86e-15*__import__("math").exp(-5.31/3))
    _, status = m.benchmark(2074, 3.0)
    assert "NOT_INDEPENDENT" in status
    rows = [
        {"reaction_id":"2072", "Te_eV":"3", "k_lookup_m3_s":str(1.1*k2072)},
        {"reaction_id":"2073", "Te_eV":"3", "k_lookup_m3_s":str(.8*k2073)},
    ]
    report = m.compare_rate_rows(rows)
    assert report[0]["relative_deviation"] == pytest.approx(.1)
    assert report[1]["relative_deviation"] == pytest.approx(-.2)
    assert not any(r["scientific_acceptance"] for r in report)
    for te in (0, .999, 7.001, float("nan")):
        with pytest.raises(ValueError):
            m.benchmark(2073, te)
    with pytest.raises(ValueError):
        m.compare_rate_rows([rows[0], rows[0]])
    with pytest.raises(ValueError):
        m.compare_rate_rows([{"reaction_id":"2073", "Te_eV":"3", "k_lookup_m3_s":"nan"}])
    with pytest.raises(ValueError):
        m.compare_rate_rows([])
