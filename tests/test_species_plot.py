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


def _case(root: Path, times=(0., 1.e-4), *, canonical=False) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    nt = len(times)
    path = root / "native.e"
    enames = (("log_O2p", "log_Om", "log_Op") if canonical else
              ("log_ni", "log_nm", "log_nop")) + ("p", "w_O2s", "w_O", "w_Os")
    with netcdf_file(str(path), "w") as f:
        for name, count in {"time_step": nt, "num_dim": 2, "num_nodes": 4, "num_el_blk": 1,
                            "num_elem_var": len(enames), "num_nod_var": 3, "num_glo_var": 1, "len_string": 64,
                            "num_elem_in_blk1": 2, "num_nod_per_el1": 3}.items():
            f.createDimension(name, count)
        f.createVariable("time_whole", "d", ("time_step",))[:] = times
        f.createVariable("coordx", "d", ("num_nodes",))[:] = (0, 1, 0, 1)
        f.createVariable("coordy", "d", ("num_nodes",))[:] = (0, 0, 1, 1)
        _names(f.createVariable("eb_names", "c", ("num_el_blk", "len_string")), ("plasma",))
        f.createVariable("connect1", "i", ("num_elem_in_blk1", "num_nod_per_el1"))[:] = ((1, 2, 3), (2, 4, 3))
        electron_name = "log_e" if canonical else "log_ne"
        _names(f.createVariable("name_nod_var", "c", ("num_nod_var", "len_string")),
               (electron_name, "log_energy", "potential"))
        f.createVariable("vals_nod_var1", "d", ("time_step", "num_nodes"))[:] = np.full((nt, 4), -20.)
        f.createVariable("vals_nod_var2", "d", ("time_step", "num_nodes"))[:] = np.full((nt, 4), -20. + np.log(3.))
        f.createVariable("vals_nod_var3", "d", ("time_step", "num_nodes"))[:] = np.tile([0., 1., 0., 1.], (nt, 1))
        _names(f.createVariable("name_glo_var", "c", ("num_glo_var", "len_string")), ("P_rf_scaled_W_t6",))
        f.createVariable("vals_glo_var", "d", ("time_step", "num_glo_var"))[:] = np.linspace(0., 400., nt)[:, None]
        _names(f.createVariable("name_elem_var", "c", ("num_elem_var", "len_string")), enames)
        values = ((-20., -19.), (-27., -26.), (-28., -27.), (1.33, 1.34),
                  (0.1, 0.2), (0.2, 0.1), (0.1, 0.1))
        for i, (a, b) in enumerate(values, 1):
            f.createVariable(f"vals_elem_var{i}eb1", "d", ("time_step", "num_elem_in_blk1"))[:] = np.tile((a, b), (nt, 1))
    inp = root / "oxygen.i"
    inp.write_text("""[Variables]
  [ELECTRON_STATE_PLACEHOLDER]
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
""".replace("ELECTRON_STATE_PLACEHOLDER", electron_name), encoding="utf8")
    return path, inp


def test_native_8_species_and_correct_density_conversion(tmp_path):
    pytest.importorskip("matplotlib")
    exodus, inp = _case(tmp_path)
    out = tmp_path / "species.png"
    result = generate(exodus, out, inputs=(inp,), time_us=100, layout="auto")
    assert result["fields"] == ["e-", "O2+", "O-", "O+", "O2", "O2*", "O", "O*", "potential", "T_e"]
    assert result["mode"] == "2d-map"
    assert result["field_ranges"]["potential"]["units"] == "V"
    assert result["field_ranges"]["T_e"]["units"] == "eV"
    assert "log_energy" in result["field_sources"]["T_e"]
    assert result["row_capacities"] == [4, 4, 2]
    assert result["colormap"] == "rainbow"
    assert result["density_color_scale"] == "linear"
    assert all(result["field_ranges"][name]["color_scale"] == "linear" for name in result["fields"])
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



def test_canonical_exodus_density_fields_map_and_trace(tmp_path):
    """New ContinuityEq outputs can be decoded without a runtime alias flag."""
    pytest.importorskip("matplotlib")
    exodus, inp = _case(tmp_path, canonical=True)
    from physics_harness.adapters.moose.time_trace import _native_traces

    output = tmp_path / "canonical_map.png"
    result = generate(exodus, output, inputs=(inp,), time_us=100)
    assert result["fields"][:4] == ["e-", "O2+", "O-", "O+"]
    for label, field in (("e-", "log_e"), ("O2+", "log_O2p"),
                         ("O-", "log_Om"), ("O+", "log_Op")):
        assert field in result["field_sources"][label]
        assert result["species_density_ranges"][label]["max_m3"] > 0
    assert "log_energy-log_e" in result["field_sources"]["T_e"]
    assert output.stat().st_size > 1000

    traces = _native_traces(exodus, (inp,), None)
    for label, field in (("e-", "log_e"), ("O2+", "log_O2p"),
                         ("O-", "log_Om"), ("O+", "log_Op")):
        assert field in traces["sources"][label]
        assert len(traces["series"][label]) == 2
    assert "log_energy-log_e" in traces["sources"]["T_e"]


def test_exodus_rejects_ambiguous_archive_and_canonical_states(tmp_path):
    """Fail closed rather than silently favor either physical density source."""
    from physics_harness.adapters.moose.species_plot import exodus_log_name
    from physics_harness.adapters.moose.time_trace import _native_traces

    with pytest.raises(DefaultPlotError, match="ambiguous"):
        exodus_log_name(["log_ne", "log_e"], "e-")
    with pytest.raises(DefaultPlotError, match="ambiguous"):
        exodus_log_name(["log_ni", "log_O2p"], "O2+")
    with pytest.raises(DefaultPlotError, match="duplicate"):
        exodus_log_name(["log_e", "log_e"], "e-")
    assert exodus_log_name(["log_e"], "e-") == "log_e"
    assert exodus_log_name(["log_ne"], "e-") == "log_ne"
    assert exodus_log_name([], "e-") is None

    exodus, inp = _case(tmp_path / "mixed")
    with netcdf_file(str(exodus), "a") as f:
        _names(f.variables["name_nod_var"], ("log_ne", "log_e", "potential"))
    with pytest.raises(DefaultPlotError, match="ambiguous"):
        _native_species(exodus, "auto", None, None, (inp,), None)
    with pytest.raises(DefaultPlotError, match="ambiguous"):
        _native_traces(exodus, (inp,), None)


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


def test_reject_retired_mode_and_unknown_species(tmp_path):
    exodus, inp = _case(tmp_path)
    with pytest.raises(DefaultPlotError, match="mode must be"):
        generate(exodus, tmp_path / "bad.png", mode="fields", gas_temperature_k=300)
    with pytest.raises(DefaultPlotError, match="unknown Oxygen14 species"):
        generate(exodus, tmp_path / "bad.png", variables=("made_up",))


def test_weighted_native_exodus_traces_exact_rz_quadrature(tmp_path):
    from physics_harness.adapters.moose.time_trace import _native_traces

    exodus, inp = _case(tmp_path)
    report = _native_traces(exodus, (inp,), None)
    assert len(report["time_us"]) == 2
    assert report["plasma_volume_m3"] == pytest.approx(np.pi)
    assert report["series"]["e-"] == pytest.approx([N_A*np.exp(-20)]*2)
    assert report["series"]["potential"] == pytest.approx([2/3]*2, rel=1e-12)
    assert report["series"]["T_e"] == pytest.approx([2.]*2)
    assert report["series"]["power"] == pytest.approx([0, 400])
    expected_ion = N_A * (np.exp(-20)/3 + 2*np.exp(-19)/3)
    assert report["series"]["O2+"] == pytest.approx([expected_ion]*2)
    assert len(report["series"]) == 11
    assert report["sources"]["power"].startswith("actual native global P_rf_scaled_W_t6")


def test_rz_quadrature_rejects_negative_radius_and_degenerate_cell():
    from physics_harness.adapters.moose.time_trace import rz_triangle_weights

    x, y = [0, 1, 0], [0, 0, 1]
    tri, owners, volume, weights = rz_triangle_weights(x, y, [[1, 2, 3]])
    assert volume[0] == pytest.approx(np.pi/3)
    assert weights.sum() == pytest.approx(volume.sum())
    # Weighted mean radius = integral(r^2)/integral(r) = 1/2.
    assert np.dot(weights[0], np.asarray(x)[tri[0]]) / volume[0] == pytest.approx(1/2)
    with pytest.raises(DefaultPlotError, match="nonnegative radius"):
        rz_triangle_weights([-1, 1, 0], y, [[1, 2, 3]])
    with pytest.raises(DefaultPlotError, match="zero-area"):
        rz_triangle_weights([0, 1, 2], [0, 0, 0], [[1, 2, 3]])


def test_time_trace_compare_keeps_different_native_time_grids(tmp_path):
    pytest.importorskip("matplotlib")
    from physics_harness.adapters.moose.time_trace import generate_time_trace

    run_1, inp_1 = _case(tmp_path / "run_1", times=(0, 1e-4))
    run_2, inp_2 = _case(tmp_path / "run_2", times=(0, 5e-5, 1e-4))
    out = tmp_path / "compare.png"
    result = generate_time_trace(run_1.parent, out, inputs=(inp_1,),
                                 compare=run_2.parent, compare_inputs=(inp_2,),
                                 variables=("e-", "potential", "T_e", "power"),
                                 layout="2x2")
    assert result["compare"] is True
    assert result["fields"] == ["e-", "potential", "T_e", "power"]
    assert [r["timepoint_count"] for r in result["runs"]] == [2, 3]
    assert result["runs"][1]["native_time_us"] == pytest.approx([0, 50, 100])
    assert result["runs"][0]["plasma_volume_m3"] == pytest.approx(np.pi)
    assert result["row_capacities"] == [2, 2]
    assert out.stat().st_size > 2000
    assert json.loads((tmp_path/"compare.png.json").read_text())["science_acceptance"] == "NOT_EVALUATED"
    with pytest.raises(DefaultPlotError, match="compare a run to itself"):
        generate_time_trace(run_1, tmp_path/"same.png", compare=run_1)
    with pytest.raises(DefaultPlotError, match="not available in every run"):
        generate_time_trace(run_1, tmp_path/"missing.png", variables=("O2",))


def test_default_plot_mode_routing_and_cli_rejects_incompatible_compare(tmp_path):
    from physics_harness.adapters.moose.default_plot import main

    exodus, inp = _case(tmp_path)
    result = generate(exodus, tmp_path/"map.png", inputs=(inp,), mode="2d-map")
    assert result["mode"] == "2d-map" and "potential" in result["fields"]
    trace = generate(exodus, tmp_path/"trace.png", inputs=(inp,), mode="time-trace")
    assert trace["mode"] == "time-trace"
    assert len(trace["fields"]) == 11
    with pytest.raises(DefaultPlotError, match="requires --mode time-trace"):
        generate(exodus, tmp_path/"fail.png", mode="2d-map", compare=exodus)
    with pytest.raises(DefaultPlotError, match="apply to 2d-map"):
        generate(exodus, tmp_path/"fail.png", mode="time-trace", time_us=100)
    assert main(["--mode", "2d-map", "--run", str(tmp_path), "--compare", str(exodus)]) == 2
    assert main(["--mode", "time-trace", "--run", str(tmp_path), "--time-us", "100"]) == 2


def test_time_trace_no_fabrication_of_missing_neutral_or_power(tmp_path):
    from physics_harness.adapters.moose.time_trace import _native_traces

    exodus, _ = _case(tmp_path)
    report = _native_traces(exodus, (), None, power_field="unavailable_power")
    assert "O2" not in report["series"] and "O2" in report["unavailable"]
    assert "power" not in report["series"] and "power" in report["unavailable"]
    assert "unaudited power field" in report["unavailable"]["power"]
    assert "e-" in report["series"] and "potential" in report["series"]


def test_2d_map_color_scale_default_and_log_opt_in(tmp_path):
    pytest.importorskip("matplotlib")
    exodus, inp = _case(tmp_path)
    linear = generate(exodus, tmp_path / "linear.png", inputs=(inp,),
                      variables=("e-", "O2+"), time_us=100)
    assert linear["density_color_scale"] == "linear"
    assert linear["field_ranges"]["e-"]["color_scale"] == "linear"
    assert json.loads((tmp_path / "linear.png.json").read_text())["density_color_scale"] == "linear"

    log = generate(exodus, tmp_path / "log.png", inputs=(inp,),
                   variables=("e-", "potential"), time_us=100, color_scale="log")
    assert log["density_color_scale"] == "log"
    assert log["field_ranges"]["e-"]["color_scale"] == "log"
    assert log["field_ranges"]["potential"]["color_scale"] == "linear"
    with pytest.raises(DefaultPlotError, match="color-scale"):
        generate(exodus, tmp_path / "bad.png", inputs=(inp,), color_scale="symlog")


def test_linear_accepts_all_zero_density_but_log_rejects_it(tmp_path):
    pytest.importorskip("matplotlib")
    exodus, inp = _case(tmp_path)
    # Exponential underflow represents a species absent from the native state.
    with netcdf_file(str(exodus), "a") as f:
        f.variables["vals_elem_var2eb1"][:, :] = -900.
    linear = generate(exodus, tmp_path / "zero.png", inputs=(inp,),
                      variables=("O-",))
    assert linear["field_ranges"]["O-"]["min"] == 0
    assert linear["field_ranges"]["O-"]["max"] == 0
    assert linear["field_ranges"]["O-"]["color_scale"] == "linear"
    with pytest.raises(DefaultPlotError, match="all-zero species"):
        generate(exodus, tmp_path / "zero-log.png", inputs=(inp,),
                 variables=("O-",), color_scale="log")
