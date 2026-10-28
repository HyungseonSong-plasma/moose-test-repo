"""P0 characterization for experimental O2 -> O(3P) + O(1D) channel.

The channel's rate comes from a Maxwellian temperature-fit sensitivity
comparison (doi:10.1515/jaots-2017-0002), NOT validated EEPF parity.
8.4 eV electron loss is COMSOL Ar/O2 ICP Table 2 reaction 14.
"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "experiments/Issue395_powered_chemistry_ladder/build_o2_dissociation_overlay.py"
BASE = """[w_O]
[w_Os]
[log_energy]
property_name = n_e_physical
property_name = rho_neutral
property_name = w_O2_constraint
type = PhysicsElectronMeanEnergyMaterial
mean_energy = mean_en_solved
"""


def generate(tmp_path: Path, base: str = BASE, channel: str = "mixed"):
    source = tmp_path / "base.i"
    out = tmp_path / "overlay.i"
    source.write_text(base, encoding="utf-8")
    run = subprocess.run(
        [sys.executable, str(GENERATOR), "--base-input", str(source),
         "--output", str(out), "--channel", channel],
        check=False, text=True, capture_output=True,
    )
    return run, out


def expression(overlay: str, block: str) -> str:
    return overlay.split(f"  [{block}]\n", 1)[1].split("  []\n", 1)[0].split(
        "    expression = '", 1)[1].split("'\n", 1)[0]


def calc(expr: str, **variables: float) -> float:
    return eval(expr.replace("^", "**"), {"__builtins__": {}}, {"exp": math.exp, **variables})


@pytest.mark.parametrize(("te", "expected"), [
    (2.0, 3.49e-14*math.exp(-5.92/2.0)),
    (4.0, 3.49e-14*math.exp(-5.92/4.0)),
    (6.0, 3.49e-14*math.exp(-5.92/6.0)),
])
def test_literature_rate_numeric_reference(tmp_path: Path, te: float, expected: float):
    proc, path = generate(tmp_path)
    assert proc.returncode == 0, proc.stderr
    s = path.read_text(encoding="utf-8")
    assert "HOLD_CROSS_SECTION_EEPF_QUENCHING" in proc.stdout
    r = calc(expression(s, "mixed_o2_progress"), te=te, ne=1.0, co2=1.0)
    assert math.isclose(r, expected, rel_tol=2e-14)
    assert "8.4 eV" in s
    assert "doi:10.1515/jaots-2017-0002" in s


def test_exact_source_owners_and_existing_species_reuse(tmp_path: Path):
    proc, path = generate(tmp_path)
    assert proc.returncode == 0, proc.stderr
    s = path.read_text(encoding="utf-8")
    assert s.count("property_name = R_diss_O2_mixed") == 1
    assert s.count("variable = w_O\n") == 1
    assert s.count("variable = w_Os\n") == 1
    assert "type = PhysicsFVSpeciesReactionSource" in s
    assert "[Variables]" not in s
    assert "functor_names = 'rho_neutral w_O2_constraint'" in s
    assert "functor_names = 'n_e_physical c_O2_diss_mixed Te_diss_mixed_eV'" in s
    assert "electron_particle_source" not in s
    assert s.count("functor = S_electron_energy_mol_diss_mixed") == 1
    assert "O(3P)=w_O, O(1D)=w_Os" in s


@pytest.mark.parametrize("progress", [1e-12, 1.0, 1e7])
def test_oxygen_heavy_mass_charge_and_energy_ledger(tmp_path: Path, progress: float):
    proc, path = generate(tmp_path)
    assert proc.returncode == 0, proc.stderr
    s = path.read_text(encoding="utf-8")
    O = calc(expression(s, "mixed_o3p_mass_source"), R=progress)
    Os = calc(expression(s, "mixed_o1d_mass_source"), R=progress)
    O2 = calc(expression(s, "mixed_o2_mass_sink_implicit"), R=progress)
    elec_energy = calc(expression(s, "mixed_electron_energy_sink"), R=progress)
    assert math.isclose(O, .016*progress, rel_tol=2e-14)
    assert math.isclose(Os, .016*progress, rel_tol=2e-14)
    assert math.isclose(O2, -.032*progress, rel_tol=2e-14)
    assert math.isclose(O+Os+O2, 0, abs_tol=max(1e-24,progress*1e-17))
    assert math.isclose(elec_energy, -8.4*progress, rel_tol=2e-14)
    assert O > 0 and Os > 0 and O2 < 0 and elec_energy < 0
    assert not math.isclose(O+O2, 0.0, abs_tol=1e-25)
    assert not math.isclose(O+Os-0.016*progress, 0, abs_tol=1e-25)


@pytest.mark.parametrize("bad", [
    BASE.replace("[w_Os]", ""),
    BASE.replace("property_name = rho_neutral", ""),
    BASE.replace("mean_energy = mean_en_solved", ""),
    BASE+"property_name = R_diss_O2_mixed\n",
    BASE+"property_name = S_Os_mass_diss_mixed\n",
])
def test_required_species_and_progress_owner_fail_closed(tmp_path: Path, bad: str):
    proc, path = generate(tmp_path, bad)
    assert proc.returncode != 0
    assert not path.exists()


def test_existing_ground_state_default_identical(tmp_path: Path):
    proc, path = generate(tmp_path, channel="ground")
    assert proc.returncode == 0, proc.stderr
    s = path.read_text(encoding="utf-8")
    assert "property_name = R_diss_O2\n" in s
    assert "source = S_O_mass_diss\n" in s
    assert "variable = w_Os\n" not in s
    assert "R_diss_O2_mixed" not in s
