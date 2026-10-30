"""Synthetic-only Reaction 2259 O2+ dissociative-recombination acquisition tests.

No experimental cross-section samples are embedded. Reference rate coefficient
is a benchmark only, from Peverall et al. 2001 DOI 10.1063/1.1349079.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
from pathlib import Path

import pytest

MODULE = (Path(__file__).resolve().parents[2] /
    "experiments/Issue395_powered_chemistry_ladder/collect_o2plus_dr_2259.py")
spec = importlib.util.spec_from_file_location("o2plus_dr_2259", MODULE)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def synthetic_csv() -> str:
    # Purely invented QA values, deliberately not cited as measured Peverall data.
    energies = [0.001, .003, .006, .02, .05, .1, .3, .5, 1., 2., 3.]
    rows = ["collision_energy_eV,cross_section_cm2"]
    rows += [f"{e:.9g},{(1e-14/e):.12g}" for e in energies]
    return "\n".join(rows) + "\n"


def test_2259_synthetic_source_conversion_sha_and_non_overwrite(tmp_path) -> None:
    original = tmp_path / "authorized_local_o2plus_dr.csv"
    original.write_text(synthetic_csv(), encoding="utf-8")
    dest = tmp_path / "local_cross_sections"
    manifest = mod.prepare(original, dest, "2026-10-30")
    assert manifest["reaction_id"] == 2259
    assert manifest["initial_ion_state"] == "O2+(X2Pi_g,v=0)"
    assert manifest["source_doi"] == "10.1063/1.1349079"
    assert manifest["source_sha256"] == hashlib.sha256(original.read_bytes()).hexdigest()
    assert manifest["point_count"] == 11
    assert manifest["electron_energy_loss_eV"] is None
    assert manifest["species_branching_verified"] is False
    assert manifest["reaction_rate_table_created"] is False
    assert (dest / mod.OUTPUT_CSV).is_file()
    assert (dest / mod.OUTPUT_MANIFEST).is_file()
    with (dest / mod.OUTPUT_CSV).open(newline="", encoding="utf-8") as f:
        data = list(csv.DictReader(f))
    assert len(data) == 11
    assert float(data[0]["collision_energy_eV"]) == 0.001
    assert float(data[0]["cross_section_m2"]) == pytest.approx(1e-11 * 1e-4)
    with pytest.raises(FileExistsError):
        mod.prepare(original, dest, "2026-10-30")
    assert mod.prepare(original, dest, "2026-10-30", replace=True) == manifest


@pytest.mark.parametrize("broken", [
    lambda s: s.replace("collision_energy_eV", "electron_temp_eV"),
    lambda s: s.replace("0.001,", "0,"),
    lambda s: s.replace("0.003,", "0.001,"),
    lambda s: s.replace("0.001,", "nan,"),
    lambda s: s.replace("0.001,", "-0.001,"),
    lambda s: s.replace("1e", "-1e"),
    lambda s: "\n".join(s.splitlines()[:6]) + "\n",
    lambda s: s.replace("3,", "0.1,", 1),
])
def test_2259_import_mutation_controls(broken) -> None:
    with pytest.raises(ValueError):
        mod.parse_author_data(broken(synthetic_csv()))


def test_2259_reference_formula_is_comparator_only() -> None:
    assert mod.benchmark_k(300.0) == pytest.approx(2.4e-13)
    records = [
        {"Te_K": "300", "k_lookup_m3_s": str(2.64e-13)},
        {"Te_K": "600", "k_lookup_m3_s": str(2.4e-13*(.5)**.70)},
    ]
    out = mod.compare_boltzmann_rates(records)
    assert out[0]["relative_deviation"] == pytest.approx(.1)
    assert out[1]["relative_deviation"] == pytest.approx(0.)
    assert all(x["acceptance"] == "numerical comparison only" for x in out)
    with pytest.raises(ValueError):
        mod.benchmark_k(200.0)
    with pytest.raises(ValueError):
        mod.compare_boltzmann_rates([])
    with pytest.raises(ValueError):
        mod.compare_boltzmann_rates(records[:1]*2)
    with pytest.raises(ValueError):
        mod.compare_boltzmann_rates([{"Te_K": "300", "k_lookup_m3_s": "inf"}])
