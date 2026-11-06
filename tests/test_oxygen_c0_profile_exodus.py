"""Native-format synthetic Exodus negative/positive controls, no solver evidence."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.io import netcdf_file

from experiments.Issue395_powered_chemistry_ladder.chemistry_off_c0 import EXPECTED_SOURCE, EXPECTED_PHYSICS, expected_grid_ns
from experiments.Issue395_powered_chemistry_ladder.electron_profile_exodus import extract, ElectronProfileError


def write_chars(var, names, length=48):
    arr = np.zeros((len(names), length), dtype="S1")
    for i, name in enumerate(names):
        arr[i, :len(name)] = np.frombuffer(name.encode(), dtype="S1")
    var[:] = arr


def fixture_case(tmp_path: Path):
    manifest = tmp_path / "c0.json"
    manifest.write_text(json.dumps({"phase":"P0_STATIC_CANDIDATE_ONLY", "source_harness_expected_sha":EXPECTED_SOURCE,
        "physics_app_expected_sha": EXPECTED_PHYSICS, "active_cli_input_files":["plasma.i","rf.i"],"power_target_W":400}))
    path=tmp_path/"native.e"
    ns=np.asarray(expected_grid_ns(),dtype=float)
    with netcdf_file(str(path), "w") as f:
        for k,n in {"time_step":461,"num_nodes":4,"num_el_blk":1,"len_string":48,
                     "num_nod_var":2,"num_elem_in_blk1":1,"num_nod_per_el1":3}.items():
            f.createDimension(k,n)
        f.createVariable("time_whole","d",("time_step",))[:] = ns*1e-9
        f.createVariable("coordx","d",("num_nodes",))[:] = [0.0,0.01,0.02,0.03]
        f.createVariable("coordy","d",("num_nodes",))[:] = [0.01,0.01,0.01,0.01]
        write_chars(f.createVariable("eb_names","c",("num_el_blk","len_string")),["plasma"])
        f.createVariable("connect1","i",("num_elem_in_blk1","num_nod_per_el1"))[:] = [[1,2,3]]
        write_chars(f.createVariable("name_nod_var","c",("num_nod_var","len_string")),["log_ne","log_energy"])
        ne = np.full((461,4),-10.0)
        energy = ne + np.log(3.0)
        f.createVariable("vals_nod_var1","d",("time_step","num_nodes"))[:] = ne
        f.createVariable("vals_nod_var2","d",("time_step","num_nodes"))[:] = energy
    return path,manifest,tmp_path/"profile"


def test_extracts_native_2d_profile_without_extrapolation(tmp_path):
    path,manifest,out=fixture_case(tmp_path)
    summary=extract(path,manifest,out)
    assert summary["status"]=="NATIVE_EXODUS_FIELDS_EXTRACTED_NOT_SCIENCE_PASS"
    assert summary["plasma_node_count"]==3
    assert summary["timepoint_count"]==461
    assert len((out/"electron_profile_2d.csv").read_text().splitlines())==28
    assert summary["observations"][-1]["mean_energy_min_eV"]==pytest.approx(3.0)
    with pytest.raises(ElectronProfileError,match="overwrite"):
        extract(path,manifest,out)


def test_rejects_wrong_source_or_unverified_manifest(tmp_path):
    path,manifest,out=fixture_case(tmp_path)
    data=json.loads(manifest.read_text());data["power_target_W"]=1000
    manifest.write_text(json.dumps(data))
    with pytest.raises(ElectronProfileError,match="manifest class"):
        extract(path,manifest,out)
    assert not out.exists()


def test_rejects_wrong_timegrid(tmp_path):
    path,manifest,out=fixture_case(tmp_path)
    with netcdf_file(str(path),"a") as f:
        t=np.asarray(f.variables["time_whole"][:]).copy();t[40]+=0.5e-9
        f.variables["time_whole"][:]=t
    with pytest.raises(ElectronProfileError,match="timeline"):
        extract(path,manifest,out)
