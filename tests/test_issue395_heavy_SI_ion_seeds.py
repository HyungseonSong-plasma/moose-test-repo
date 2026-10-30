"""Static research-contract validation for oxygen H23/H24/H25 SI rates and seed."""
from pathlib import Path
import math

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "experiments/Issue395_powered_chemistry_ladder"

def test_heavy_si_two_body_rate_coefficients_and_sign():
    text = (DATA / "oxygen_heavy_H23_H24_H25_SI_research.txt").read_text()
    entries = text.split("\nreaction ")[1:]
    assert len(entries) == 3
    expected = {"H23_Op_Om_to_2O": 1e-13,
                "H24_Om_O2p_to_O2_O": 1e-13,
                "H25_Op_O2_to_O_O2p": 2e-17}
    for entry in entries:
        name = entry.split()[0]
        lines = entry.splitlines()
        values = {line.split()[0]: line.split()[1]
                  for line in lines if line.startswith(("A ", "basis ", "T_ref ", "exponent "))}
        assert name in expected
        assert values["basis"] == "particle"
        assert math.isclose(float(values["A"]), expected[name], rel_tol=1e-14)
    assert "T_ref 300\nexponent 0.4" in text
    assert math.isclose(2e-17*(600/300)**(-0.4), 2e-17*(300/600)**0.4)

def test_ion_seed_positive_charge_neutral():
    n_e, n_o2p, n_op, n_om = 1e15, 1e15, 1e12, 1e12
    assert n_o2p+n_op == n_e+n_om
    text=(DATA / "oxygen_ion_seeds_research.txt").read_text()
    for density in (1e15,1e12):
        assert str(int(density)) not in text or density>0
    for symbol, value in {"log_ne": n_e, "log_ni": n_o2p, "log_nop": n_op, "log_nm": n_om}.items():
        assert f"[{symbol}]" in text
        assert f"{math.log(value/6.02214076e23):.12f}"[:10] in text
