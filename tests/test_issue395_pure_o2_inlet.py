"""P0 positive/negative inlet controls; no change to interior initial mixture."""
import importlib.util
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "experiments/Issue395_powered_chemistry_ladder/set_pure_o2_inlet.py"
spec = importlib.util.spec_from_file_location("pure_o2", SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fixture():
    lines = [
        "[Variables]\n",
        "  [w_O]\n    initial_condition = 1.7455280139995249e-6\n  []\n",
        "  [w_Os]\n    initial_condition = 0.12371134020618557\n  []\n",
        "  [w_O2s]\n    initial_condition = 0.051546391752577324\n  []\n",
        "[]\n[FunctorMaterials]\n  [neutral_O2_constraint]\n",
        "    property_name = w_O2_constraint\n    expression = '1.0-s-o-a'\n  []\n[]\n",
        "[BCs]\n",
        "  [neutral_inlet_mass]\n    type = WCNSFVMassFluxBC\n    mdot_pp = neutral_inlet_mdot\n    boundary = inlet\n  []\n",
    ]
    for tag, var, flux in (
        ("O2s", "w_O2s", "neutral_inlet_mdot_O2s"),
        ("O", "w_O", "neutral_inlet_mdot_O"),
        ("Os", "w_Os", "neutral_inlet_mdot_Os"),
    ):
        lines.append(
            f"  [neutral_inlet_{tag}]\n    type = WCNSFVScalarFluxBC\n"
            f"    variable = {var}\n    passive_scalar = {var}\n"
            f"    boundary = inlet\n    scalar_flux_pp = {flux}\n  []\n"
        )
    lines.append("[]\n[Postprocessors]\n")
    for key,value in mod.BASE.items():
        lines.append(f"  [{key}]\n    type = Receiver\n    default = {value:.17g}\n  []\n")
    lines.append("[]\n")
    return "".join(lines)


def test_exact_receiver_mutation():
    original = fixture()
    modified = mod.apply(original)
    mod.verify(modified, mod.PURE)
    assert "initial_condition = 1.7455280139995249e-6" in modified
    assert "initial_condition = 0.12371134020618557" in modified
    assert "initial_condition = 0.051546391752577324" in modified
    assert mod.receiver_values(modified)["neutral_inlet_mdot"] == mod.TOTAL_MDOT
    assert mod.receiver_values(modified)["neutral_inlet_mdot_O2"] == mod.TOTAL_MDOT
    for name in ("neutral_inlet_mdot_O2s", "neutral_inlet_mdot_O", "neutral_inlet_mdot_Os"):
        assert mod.receiver_values(modified)[name] == 0.0
    # Inverse restore exactly the original bytes using only receiver blocks.
    restored = modified
    for k,v in mod.BASE.items():
        if k == "neutral_inlet_mdot":
            continue
        old=f"  [{k}]\n    type = Receiver\n    default = {mod.PURE[k]:.17g}\n  []\n"
        new=f"  [{k}]\n    type = Receiver\n    default = {v:.17g}\n  []\n"
        assert restored.count(old)==1
        restored=restored.replace(old,new)
    assert restored == original


@pytest.mark.parametrize("old,new", [
    ("scalar_flux_pp = neutral_inlet_mdot_O\n", "scalar_flux_pp = neutral_inlet_mdot_O2\n"),
    ("[neutral_inlet_mdot_O]\n", "[neutral_inlet_mdot_O2]\n"),
    ("    type = Receiver\n", "    type = ConstantPostprocessor\n"),
    ("default = 1.9995862855975097e-07", "default = -1"),
    ("expression = '1.0-s-o-a'", "expression = '0.0-s-o-a'"),
])
def test_invalid_inlet_rejected(old,new):
    original = fixture()
    assert old in original
    with pytest.raises(ValueError):
        mod.apply(original.replace(old,new,1))


def test_repeated_application_fails():
    with pytest.raises(ValueError):
        mod.apply(mod.apply(fixture()))


def test_declared_total_is_sum_of_baseline_species():
    assert math.isclose(
        sum(v for k,v in mod.BASE.items() if k != "neutral_inlet_mdot"),
        mod.TOTAL_MDOT, rel_tol=1e-13)
