#!/usr/bin/env python3
"""After pinned Issue397 ground prepare, add mixed channel, optional detachment, exact O initial."""
from __future__ import annotations
import argparse
import importlib.util
import pathlib
import re
import subprocess
import sys

CHEM = pathlib.Path("experiments/Issue395_powered_chemistry_ladder")
INPUT = CHEM / "rf_elastic_diss_ion_ei20_ei01_1000w_adjacent_sheath_wall_closed_100us_dt1000ns.i"
GROUND = CHEM / "o2_dissociation_1000w_100us_dt1000ns_overlay.i"
MIXED = CHEM / "o2_dissociation_mixed_1000w_100us_dt1000ns_overlay.i"
DETACH = CHEM / "o_minus_e_detachment_1000w_100us_dt1000ns_overlay.i"
RESULT = CHEM / "results_rf_elastic_diss_ion_ei20_ei01_1000w_adjacent_sheath_wall_closed_100us_dt1000ns_pure_o2_inlet_step1"
TARGET = 5e18

def load_helper(path):
    spec = importlib.util.spec_from_file_location("o3p_eos", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--detachment", choices=("off","on"), required=True)
    p.add_argument("--helper", type=pathlib.Path, required=True)
    p.add_argument("--detachment-builder",type=pathlib.Path,required=True)
    a = p.parse_args()
    assert INPUT.exists() and GROUND.exists() and (RESULT / "prep/pure_o2_inlet.log").exists()
    before = INPUT.read_text()
    assert "    property_name = R_diss_O2\n" in GROUND.read_text()
    assert "R_diss_O2_mixed" not in GROUND.read_text()
    helper = load_helper(a.helper)
    updated = helper.change_to_target_number_density(before, TARGET)
    helper.verify_target_number_density(updated, TARGET)
    # One-line-only mutation of the initial neutral O(3P) fraction.
    changed_lines = [(i,old,new) for i,(old,new) in enumerate(zip(before.splitlines(),updated.splitlines()),1) if old!=new]
    assert len(before.splitlines())==len(updated.splitlines())
    assert len(changed_lines)==1, changed_lines
    assert re.fullmatch(r"\s*initial_condition = [-0-9.eE+]+",changed_lines[0][1])
    assert re.fullmatch(r"\s*initial_condition = [-0-9.eE+]+",changed_lines[0][2])
    (RESULT / "prep/input_before_o3p_5e18.i").write_text(before)
    INPUT.write_text(updated)
    subprocess.run(
        [sys.executable,str(CHEM/"set_pure_o2_inlet.py"),"--input",str(INPUT),"--verify"],check=True)
    subprocess.run(
        [sys.executable,str(CHEM/"build_o2_dissociation_overlay.py"),"--base-input",str(CHEM/"a0_full_icp.i"),
         "--channel","mixed","--output",str(MIXED)],check=True)
    mixed = MIXED.read_text()
    assert mixed.count("property_name = R_diss_O2_mixed")==1
    assert "    property_name = R_diss_O2\n" not in mixed
    if a.detachment == "on":
        subprocess.run([sys.executable,str(a.detachment_builder),"--base-input",str(CHEM/"a0_full_icp.i"),
                        "--output",str(DETACH)],check=True)
        assert DETACH.read_text().count("property_name = R_detach_Om")==1
    else:
        DETACH.write_text("# Case A: EDETACH_OM explicitly disabled.\n")
        assert "R_detach_Om" not in DETACH.read_text()
    helper.verify_target_number_density(INPUT.read_text(),TARGET)
    (RESULT / "prep/initial_o3p_5e18.txt").write_text(
        f"n_O3P_m3={TARGET:.17g}\nold_line={changed_lines[0][1].strip()}\nnew_line={changed_lines[0][2].strip()}\n"
        f"diss_ground=ON\ndiss_mixed=ON\nEDETACH_OM={a.detachment.upper()}\n"
        "source_pinned=aa81c1ca1d52e9431b56682b227fe96aa3a305cd\n")
    print(f"ISSUE395_BOTH_DISS_N5E18_{a.detachment.upper()}_EXACT_INPUT_PASS")

if __name__ == "__main__":
    main()
