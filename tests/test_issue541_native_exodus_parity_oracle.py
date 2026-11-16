"""Synthetic Exodus negative controls for the tiny Native parity oracle."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.io import netcdf_file

SCRIPT = Path(__file__).resolve().parents[1] / "experiments/Issue402_plasma_dsl_g1/compare_native_outputs.py"


def load():
    spec = importlib.util.spec_from_file_location("issue541_native_parity_oracle", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _names(exodus, key, names):
    exodus.createDimension(f"{key}_count", len(names))
    exodus.createDimension(f"{key}_chars", 32)
    char = exodus.createVariable(key, "c", (f"{key}_count", f"{key}_chars"))
    char[:] = np.array([list(name.ljust(32)) for name in names], dtype="S1")


def make_exodus(path, *, nodes=("log_e",), nodal_values=None,
                elems=(), elem_values=None, globals_=(), glo_values=None,
                x=(0., 1.), block_id=7, omitted_values=(),
                extra_physical=None):
    with netcdf_file(path, "w") as ex:
        ex.createDimension("time_step", 2)
        ex.createDimension("num_nodes", 2)
        ex.createVariable("time_whole", "d", ("time_step",))[:] = [0., 1.]
        ex.createVariable("coordx", "d", ("num_nodes",))[:] = x
        if nodes:
            _names(ex, "name_nod_var", nodes)
            for i, name in enumerate(nodes, 1):
                data = (nodal_values or {}).get(name, [1., 2.])
                if f"vals_nod_var{i}" not in omitted_values:
                    ex.createVariable(f"vals_nod_var{i}", "d", ("time_step", "num_nodes"))[:] = [data, data]
        if elems:
            _names(ex, "name_elem_var", elems)
            ex.createDimension("num_el_blk", 1)
            ex.createDimension("num_el_in_blk1", 1)
            ex.createVariable("eb_prop1", "i", ("num_el_blk",))[:] = [block_id]
            ex.createVariable("connect1", "i", ("num_el_in_blk1", "num_nodes"))[:] = [[1, 2]]
            for i, name in enumerate(elems, 1):
                value = (elem_values or {})[name]
                if f"vals_elem_var{i}eb1" not in omitted_values:
                    ex.createVariable(f"vals_elem_var{i}eb1", "d", ("time_step", "num_el_in_blk1"))[:] = [[value], [value]]
        if globals_:
            _names(ex, "name_glo_var", globals_)
            ex.createDimension("num_glo_var", len(globals_))
            value = [float((glo_values or {})[name]) for name in globals_]
            ex.createVariable("vals_glo_var", "d", ("time_step", "num_glo_var"))[:] = [value, value]
        if extra_physical is not None:
            ex.createVariable(extra_physical, "d", ("time_step", "num_nodes"))[:] = [[9., 10.], [9., 10.]]
    return path


def compare(tmp_path, **kwargs):
    ref = make_exodus(tmp_path / "ref.e", **kwargs.pop("ref", {}))
    new = make_exodus(tmp_path / "new.e", **kwargs.pop("new", {}))
    out = tmp_path / "report.json"
    result = subprocess.run([sys.executable, str(SCRIPT), "--baseline", str(ref),
                             "--candidate", str(new), "--output", str(out)],
                            capture_output=True, text=True)
    assert out.exists()
    return result, json.loads(out.read_text())


def test_identical_arrays_pass(tmp_path):
    result, report = compare(tmp_path)
    assert result.returncode == 0, result.stderr
    assert report["result"] == "TINY_DIFFUSION_NATIVE_NUMERICAL_PARITY_PASS"
    assert report["scope"].startswith("tiny FEM+FV")
    assert report["direct_jacobian_matrix_comparison"] == "NOT_EVALUATED"


def test_extra_candidate_nodal_field_rejected(tmp_path):
    result, report = compare(tmp_path,
                             ref={"nodes": ("log_e",)},
                             new={"nodes": ("log_e", "extra_state"),
                                  "nodal_values": {"log_e": [1., 2.],
                                                   "extra_state": [900., 901.]}})
    assert result.returncode != 0
    assert report["result"] == "NATIVE_PARITY_NOT_PROVEN"
    assert "identity metadata differs" in report["reason"]


@pytest.mark.parametrize("family", ["nodal", "elemental"])
def test_identically_missing_named_physical_field_rejected(tmp_path, family):
    """Old oracle falsely passed when both files omitted the same named field."""
    if family == "nodal":
        options = {"nodes": ("log_e", "unread_state"),
                   "omitted_values": ("vals_nod_var2",)}
    else:
        options = {"elems": ("ion_density", "unread_state"),
                   "elem_values": {"ion_density": 5., "unread_state": 9.},
                   "omitted_values": ("vals_elem_var2eb1",)}
    result, report = compare(tmp_path, ref=options, new=options)
    assert result.returncode != 0
    assert report["result"] == "NATIVE_PARITY_NOT_PROVEN"
    assert f"Exodus {family} names without values" in report["reason"]
    assert "unread_state" in report["reason"]


@pytest.mark.parametrize("on_both", [False, True])
def test_unsupported_exodus_physical_family_cannot_false_pass(tmp_path, on_both):
    """Unknown vals_* arrays must never be silently discarded."""
    unknown = {"extra_physical": "vals_nset_var1ns1"}
    result, report = compare(
        tmp_path, ref=unknown if on_both else {}, new=unknown)
    assert result.returncode != 0
    assert report["result"] == "NATIVE_PARITY_NOT_PROVEN"
    assert "Unsupported Exodus physical field" in report["reason"]
    assert "vals_nset_var1ns1" in report["reason"]


def test_reordered_named_elemental_and_global_fields_pass(tmp_path):
    kwargs = {"elem_values": {"ion_density": 5., "temperature": 30.},
              "glo_values": {"power": 400., "charge": 3.}}
    result, report = compare(
        tmp_path,
        ref={"elems": ("ion_density", "temperature"), "globals_": ("power", "charge"), **kwargs},
        new={"elems": ("temperature", "ion_density"), "globals_": ("charge", "power"), **kwargs},
    )
    assert result.returncode == 0, result.stderr
    assert report["result"] == "TINY_DIFFUSION_NATIVE_NUMERICAL_PARITY_PASS"


def test_changed_elemental_field_rejected_even_after_reorder(tmp_path):
    result, report = compare(
        tmp_path,
        ref={"elems": ("ion_density", "temperature"),
             "elem_values": {"ion_density": 5., "temperature": 30.}},
        new={"elems": ("temperature", "ion_density"),
             "elem_values": {"ion_density": 5., "temperature": 31.}},
    )
    assert result.returncode != 0
    assert "Numerical discrepancy" in report["reason"]


def test_mesh_coordinate_mismatch_rejected(tmp_path):
    result, report = compare(tmp_path, new={"x": (0., 2.)})
    assert result.returncode != 0
    assert "Numerical discrepancy" in report["reason"]


def test_nonfinite_field_rejected(tmp_path):
    result, report = compare(tmp_path, new={"nodal_values": {"log_e": [float("nan"), 2.]}})
    assert result.returncode != 0
    assert "nonfinite" in report["reason"]
