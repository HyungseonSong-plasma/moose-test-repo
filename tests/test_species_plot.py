"""P0 synthetic native-Exodus controls for species densities (not solver evidence)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.io import netcdf_file

from physics_harness.adapters.moose.default_plot import generate, DefaultPlotError
from physics_harness.adapters.moose.species_plot import _native_species, N_A


def _names(var, names, nch=64):
    arr = np.zeros((len(names), nch), dtype="S1")
    for i, s in enumerate(names):
        arr[i, :len(s)] = np.frombuffer(s.encode(), dtype="S1")
    var[:] = arr


def _case(root: Path) -> tuple[Path, Path]:
    path = root / "native.e"
    enames = ("log_ni", "log_nm", "log_nop", "p", "w_O2s", "w_O", "w_Os")
    with netcdf_file(str(path), "w") as f:
        for name, count in {"time_step": 2, "num_dim": 2, "num_nodes": 4, "num_el_blk": 1,
                            "num_elem_var": len(enames), "num_nod_var": 1, "len_string": 64,
                            "num_elem_in_blk1": 2, "num_nod_per_el1": 3}.items():
            f.createDimension(name, count)
        f.createVariable("time_whole", "d", ("time_step",))[:] = (0, 1e-4)
        f.createVariable("coordx", "d", ("num_nodes",))[:] = (0, 1, 0, 1)
        f.createVariable("coordy", "d", ("num_nodes",))[:] = (0, 0, 1, 1)
        _names(f.createVariable("eb_names", "c", ("num_el_blk", "len_string")), ("plasma",))
        f.createVariable("connect1", "i", ("num_elem_in_blk1", "num_nod_per_el1"))[:] = ((1, 2, 3), (2, 4, 3))
        _names(f.createVariable("name_nod_var", "c", ("num_nod_var", "len_string")), ("log_ne",))
        f.createVariable("vals_nod_var1", "d", ("time_step", "num_nodes"))[:] = np.full((2, 4), -20.)
        _names(f.createVariable("name_elem_var", "c", ("num_elem_var", "len_string")), enames)
        values = ((-20., -19.), (-27., -26.), (-28., -27.), (1.33, 1.34),
                  (0.1, 0.2), (0.2, 0.1), (0.1, 0.1))
        for i, (a, b) in enumerate(values, 1):
            f.createVariable(f"vals_elem_var{i}eb1", "d", ("time_step", "num_elem_in_blk1"))[:] = ((a, b), (a, b))
    inp = root / "oxygen.i"
    inp.write_text("""[Variables]
  [log_ne]
  []
[]
[FunctorMaterials]
  [constants]
    prop_names = 'p_fixed T_g_fixed carrier_one'
    prop_values = '1.33 300 1'
  []
  [neutral_O2_constraint]
    type = ADParsedFunctorMaterial
    property_name = w_O2_constraint
    functor_names = 'w_O2s w_O w_Os'
    functor_symbols = 's o a'
    expression = '1.0-s-o-a'
  []
  [neutral_mean_molar_mass]
    type = ADParsedFunctorMaterial
    property_name = Mn_neutral
    functor_names = 'w_O2_constraint w_O2s w_O w_Os'
    functor_symbols = 'm0 m1 m2 m3'
    expression = '1.0/(m0/0.032+m1/0.032+m2/0.016+m3/0.016)'
  []
  [neutral_density]
    type = ADParsedFunctorMaterial
    property_name = rho_neutral
    functor_names = 'p Mn_neutral T_g_fixed'
    functor_symbols = 'prs mol tmp'
    expression = 'prs*mol/(8.31446*tmp)'
  []
[]
""", encoding="utf8")
    return path, inp


def test_native_8_species_and_correct_density_conversion(tmp_path):
    pytest.importorskip("matplotlib")
    exodus, inp = _case(tmp_path)
    out = tmp_path / "species.png"
    result = generate(exodus, out, inputs=(inp,), time_us=100, layout="auto")
    assert result["fields"] == ["e-", "O2+", "O-", "O+", "O2", "O2*", "O", "O*"]
    assert result["row_capacities"] == [4, 4]
    assert result["colormap"] == "hsv"
    assert result["temperature_k"] == 300
    assert result["plasma_node_count"] == 4 and result["triangle_count"] == 2
    assert result["species_density_ranges"]["e-"]["max_m3"] == pytest.approx(N_A * np.exp(-20))
    assert result["species_density_ranges"]["O2+"]["min_m3"] == pytest.approx(N_A * np.exp(-20))
    assert result["species_density_ranges"]["O2"]["min_m3"] > 0
    assert result["species_density_ranges"]["O2"]["value_location"] == "elemental"
    assert out.stat().st_size > 1000
    assert json.loads((tmp_path / "species.png.json").read_text())["science_acceptance"] == "NOT_EVALUATED"
    with pytest.raises(DefaultPlotError, match="overwrite"):
        generate(exodus, out, inputs=(inp,))


def test_missing_temperature_does_not_fabricate_neutrals(tmp_path):
    exodus, inp = _case(tmp_path)
    data = _native_species(exodus, "auto", None, None, (), None)
    assert list(data["species"]) == ["e-", "O2+", "O-", "O+"]
    assert "O2" in data["unavailable"]
    with pytest.raises(DefaultPlotError, match="requested species unavailable"):
        generate(exodus, tmp_path / "must_fail.png", variables=("O2",))
    assert not (tmp_path / "must_fail.png").exists()


def test_explicit_temperature_and_species_order(tmp_path):
    pytest.importorskip("matplotlib")
    exodus, _ = _case(tmp_path)
    out = tmp_path / "two.svg"
    result = generate(exodus, out, gas_temperature_k=300, variables=("O", "e-"), layout="1x2", cmap="plasma")
    assert result["fields"] == ["O", "e-"]
    assert result["row_capacities"] == [2] and result["colormap"] == "plasma"
    assert result["temperature_source"] == "explicit --gas-temperature-k"


def test_reject_inconsistent_temperature_and_invalid_fractions(tmp_path):
    exodus, inp = _case(tmp_path)
    with pytest.raises(DefaultPlotError, match="contradicts"):
        generate(exodus, tmp_path / "bad.png", inputs=(inp,), gas_temperature_k=450)
    with netcdf_file(str(exodus), "a") as f:
        f.variables["vals_elem_var5eb1"][1, :] = [2, 2]
    with pytest.raises(DefaultPlotError, match="invalid neutral mass fraction"):
        generate(exodus, tmp_path / "bad2.png", inputs=(inp,))


def test_retains_legacy_raw_fields_mode(tmp_path):
    exodus, inp = _case(tmp_path)
    with pytest.raises(DefaultPlotError, match="only applies to species"):
        generate(exodus, tmp_path / "bad.png", mode="fields", gas_temperature_k=300)
    with pytest.raises(DefaultPlotError, match="unknown Oxygen14 species"):
        generate(exodus, tmp_path / "bad.png", variables=("made_up",))
