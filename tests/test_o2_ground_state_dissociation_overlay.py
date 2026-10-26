"""P0 characterization of the selected ground-state O2 dissociation overlay.

Independent rate anchors come from Zhao et al., Phys. Plasmas 31, 083507
(2024), Table I (4), DOI:10.1063/5.0214357. The effective 6.0 eV
electron-energy loss is COMSOL Ar/O2 ICP, Table 2, reaction 13.
Neither the 2.98 eV fit scale nor 6.0 eV effective loss is the
thermochemical threshold (~5.12 eV).
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
property_name = w_O2_constraint
property_name = n_e_physical
type = PhysicsElectronMeanEnergyMaterial
mean_energy = mean_en_solved
[log_energy]
"""


def build(tmp_path: Path, base: str = BASE) -> tuple[subprocess.CompletedProcess[str], Path]:
    src = tmp_path / "base.i"
    target = tmp_path / "diss.i"
    src.write_text(base, encoding="utf-8")
    run = subprocess.run(
        [sys.executable, str(GENERATOR), "--base-input", str(src), "--output", str(target)],
        text=True,
        capture_output=True,
        check=False,
    )
    return run, target


def expression(generated: str, name: str) -> str:
    block = generated.split(f"  [{name}]\n", 1)[1].split("  []\n", 1)[0]
    return block.split("    expression = '", 1)[1].split("'\n", 1)[0]


def evaluate(expr: str, **variables: float) -> float:
    # Evaluate only the deterministic generated arithmetic with no builtins.
    return eval(expr.replace("^", "**"), {"__builtins__": {}}, {"exp": math.exp, **variables})


@pytest.mark.parametrize(
    ("te", "expected"),
    [(2.0, 2.7283101303374e-16), (4.0, 4.9341974617953e-16)],
)
def test_ground_state_rate_matches_independent_anchors(tmp_path: Path, te: float, expected: float) -> None:
    run, target = build(tmp_path)
    assert run.returncode == 0, run.stderr
    generated = target.read_text(encoding="utf-8")
    rate = expression(generated, "diss_o2_progress")
    assert math.isclose(evaluate(rate, ne=1.0, co2=1.0, te=te), expected, rel_tol=1e-12)
    assert "te^(-0.22)" in rate
    assert "exp(-2.98/te)" in rate
    assert "12.62" not in generated
    assert "rate_fit_energy_eV=2.98" in run.stdout
    assert "effective_energy_loss_eV=6" in run.stdout


def test_energy_species_and_charge_projections_share_one_progress(tmp_path: Path) -> None:
    run, target = build(tmp_path)
    assert run.returncode == 0, run.stderr
    generated = target.read_text(encoding="utf-8")
    loss = expression(generated, "diss_electron_energy_source")
    atomic = expression(generated, "diss_o_mass_source")
    molecular = expression(generated, "diss_o2_mass_source_implicit")
    assert evaluate(loss, R=1.0) == -6.0
    assert math.isclose(evaluate(atomic, R=1.0) + evaluate(molecular, R=1.0), 0.0, abs_tol=1e-15)
    assert generated.count("property_name = R_diss_O2") == 1
    assert "electron_particle_source" not in generated
    assert "functor = S_electron_energy_molar_diss" in generated


@pytest.mark.parametrize(
    "malformed",
    [BASE.replace("mean_energy = mean_en_solved", ""), BASE + "R_diss_O2\n"],
)
def test_fail_closed_for_missing_or_duplicate_rate_owner(tmp_path: Path, malformed: str) -> None:
    run, target = build(tmp_path, malformed)
    assert run.returncode != 0
    assert not target.exists()


@pytest.mark.parametrize(
    "wrong_rate",
    [
        "1.41e-15*ne*co2*(te^(0.22))*exp(-2.98/te)",
        "1.41e-15*ne*co2*(te^(-0.22))*exp(-12.62/te)",
    ],
)
def test_historical_coefficient_mixup_fails_independent_oracle(wrong_rate: str) -> None:
    assert not math.isclose(
        evaluate(wrong_rate, ne=1.0, co2=1.0, te=2.0),
        2.7283101303374e-16,
        rel_tol=1e-3,
    )
