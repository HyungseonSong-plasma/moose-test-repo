"""P0 positive/negative characterization of reusable read-only Exodus plotting."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from scipy.io import netcdf_file

from physics_harness.adapters.moose.default_plot import DefaultPlotError, generate_fields as generate, input_fields, layout_rows


def _char_table(variable, names, size=32):
    arr = np.zeros((len(names), size), dtype="S1")
    for i, name in enumerate(names):
        arr[i, :len(name)] = np.frombuffer(name.encode(), dtype="S1")
    variable[:] = arr


def _case(tmp_path: Path):
    src = tmp_path / "native.e"
    names = tuple("abcdefgh")
    with netcdf_file(str(src), "w") as f:
        for key, length in {
            "num_dim": 2, "num_nodes": 5, "time_step": 2, "len_string": 32,
            "num_el_blk": 2, "num_nod_var": 8,
            "num_elem_in_blk1": 2, "num_nod_per_el1": 3,
            "num_elem_in_blk2": 1, "num_nod_per_el2": 3,
        }.items():
            f.createDimension(key, length)
        f.createVariable("time_whole", "d", ("time_step",))[:] = [0.0, 1.e-4]
        f.createVariable("coordx", "d", ("num_nodes",))[:] = [0., 1., 1., 0., 2.]
        f.createVariable("coordy", "d", ("num_nodes",))[:] = [0., 0., 1., 1., 0.]
        _char_table(f.createVariable("eb_names", "c", ("num_el_blk", "len_string")), ("plasma", "dielectric"))
        f.createVariable("connect1", "i", ("num_elem_in_blk1", "num_nod_per_el1"))[:] = [[1,2,3], [1,3,4]]
        f.createVariable("connect2", "i", ("num_elem_in_blk2", "num_nod_per_el2"))[:] = [[2,5,3]]
        _char_table(f.createVariable("name_nod_var", "c", ("num_nod_var", "len_string")), names)
        for i, name in enumerate(names, 1):
            f.createVariable(f"vals_nod_var{i}", "d", ("time_step", "num_nodes"))[:] = [
                np.asarray([i, i+1, i+2, i+3, 1e30], dtype=float),
                np.asarray([i+1, i+2, i+3, i+4, 1e30], dtype=float),
            ]
    input_file = tmp_path / "case.i"
    input_file.write_text("[Variables]\n" + "".join(f"  [{name}]\n  []\n" for name in names[:5])
                          + "[]\n[AuxVariables]\n  [h]\n  []\n[]\n")
    return src, input_file


def test_auto_five_eight_and_general_layout():
    assert layout_rows(5) == (3, 2)
    assert layout_rows(8) == (4, 4)
    assert layout_rows(4) == (2, 2)
    assert layout_rows(12) == (4, 4, 4)
    assert layout_rows(5, "3,2") == (3, 2)
    assert layout_rows(8, "2x4") == (4, 4)
    assert layout_rows(5, "2x4") == (4, 4)  # leave empty cells
    with pytest.raises(DefaultPlotError, match="capacity"):
        layout_rows(8, "3,2")
    for text in ("2X0", "0,5", "3;2", "unknown"):
        with pytest.raises(DefaultPlotError):
            layout_rows(5, text)


def test_primary_input_selection_vs_aux(tmp_path):
    _, source = _case(tmp_path)
    assert input_fields((source,)) == list("abcde")


def test_render_auto_primary_five(tmp_path):
    pytest.importorskip("matplotlib")
    exodus, inp = _case(tmp_path)
    out = tmp_path / "five.png"
    result = generate(exodus, out, inputs=(inp,), time_us=100.0)
    assert result["fields"] == list("abcde")
    assert result["colormap"] == "hsv"
    assert result["row_capacities"] == [3, 2]
    assert result["block"] == "plasma"
    assert result["triangle_count"] == 2
    assert result["rendered_mesh_node_count"] == 4
    assert result["time_s"] == pytest.approx(1.e-4)
    assert out.stat().st_size > 2000
    assert json.loads((tmp_path / "five.png.json").read_text())["science_acceptance"] == "NOT_EVALUATED"
    with pytest.raises(DefaultPlotError, match="overwrite"):
        generate(exodus, out, inputs=(inp,))


def test_render_eight_and_custom_subset(tmp_path):
    pytest.importorskip("matplotlib")
    exodus, inp = _case(tmp_path)
    all_eight = generate(exodus, tmp_path / "eight.png", layout="auto")
    assert all_eight["fields"] == list("abcdefgh")
    assert all_eight["row_capacities"] == [4, 4]
    custom = generate(exodus, tmp_path / "subset.svg", inputs=(inp,), variables=("b,a",), layout="1x2", cmap="plasma")
    assert custom["fields"] == ["b", "a"]
    assert custom["colormap"] == "plasma"
    assert json.loads((tmp_path / "subset.svg.json").read_text())["colormap"] == "plasma"
    assert custom["row_capacities"] == [2]
    with pytest.raises(DefaultPlotError, match="not declared"):
        generate(exodus, tmp_path / "forbid.png", inputs=(inp,), variables=("h",))


def test_reject_nonexistent_time_and_missing_field(tmp_path):
    exodus, inp = _case(tmp_path)
    with pytest.raises(DefaultPlotError, match="not a unique native timestep"):
        generate(exodus, tmp_path / "out.png", time_us=1)
    with pytest.raises(DefaultPlotError, match="range"):
        generate(exodus, tmp_path / "out.png", time_index=3)
    with pytest.raises(DefaultPlotError, match="capacity"):
        generate(exodus, tmp_path / "out.png", inputs=(inp,), layout="2x2")


def test_plot_help_has_no_scientific_dependencies(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-S", str(root / "physics_harness/adapters/moose/default_plot.py"), "--help"],
                            cwd=root, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "--layout" in result.stdout and "--variables" in result.stdout
    assert "default: hsv" in result.stdout


def test_canonical_default_plot_command_help_without_site_packages():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-S", str(root / "bin/physics.py"),
                             "default-plot", "--help"],
                            cwd=root, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "physics default-plot" in result.stdout
    assert "--layout" in result.stdout and "--exodus" in result.stdout
    assert "2d-map,time-trace" in result.stdout
    assert "species,fields" not in result.stdout
