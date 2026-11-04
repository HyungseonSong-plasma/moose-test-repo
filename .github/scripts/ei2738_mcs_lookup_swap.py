#!/usr/bin/env python3
"""Experimental MCS O- detachment / EI2738 rate-swap on the EI943-MCS 13ch case.

The MCS output labels its coefficient "O- Detachment" but does not print
complete event stoichiometry. This mapping to EI2738 is provisional, SCIENCE_HOLD.

Source 24 MCS average-energy rate points are interpolated on the original
100-point private EI943 energy grid; out-of-domain nodes use the *previous
EI2738 analytic Maxwellian formula*, not fabricated MCS extrapolation.

No change to kinetics sources, reaction inventory, electron energy loss,
other lookups, mesh, RF or the pinned original PhysicsApp.
"""
from __future__ import annotations
import argparse
import bisect
import hashlib
import json
import math
import os
from pathlib import Path
import re

ROOT=Path("experiments/Issue395_powered_chemistry_ladder")
MCS=Path("_legacy6_control/experiments/Issue395_powered_chemistry_ladder/ei2738_mcs_24case_mean_energy_rate_m3_s.txt")
LOOKUP_NAME="EI-2738_Om.txt"
REFERENCE_GRID_FILE="EI-943_O_1D.txt"
ORIGINAL_MCS_OUT_SHA256="d3db627a2d97b2bcc355c2f241b7bb231f49463cd0bb3ef6b13383166802ab08"
RESEARCH_MODE="MCS_Ominus_detachment_24case_mean_energy_lookup_with_analytic_formula_tails"
CHANNELS=["EI-01","EI-02","DISS-G","EI-16","EI-17","EI-20",
          "EI-2738","EI-407","EI-417","EI-935","EI-943","H24","H25"]
FLAG="OXYGEN_RESEARCH_EI2738_MCS"


def digest(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for block in iter(lambda: f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def parse(p,n):
    rows=[]
    for line in Path(p).read_text().splitlines():
        line=line.split("#",1)[0].strip()
        if not line: continue
        parts=line.split()
        assert len(parts)==2, "rate must have exactly two columns"
        energy,k=map(float,parts)
        assert math.isfinite(energy) and math.isfinite(k) and energy>0 and k>=0
        if rows: assert energy>rows[-1][0]
        rows.append((energy,k))
    assert len(rows)==n, f"expected {n} points, got {len(rows)}"
    return rows


def analytical_original_rate(mean_energy_eV):
    # Original overlay: T_e[eV] = 2/3 * mean_energy[eV].
    # k=2e-13 exp(-5.5/T_e), in m3/s.
    return 2e-13*math.exp(-5.5/(mean_energy_eV*(2.0/3.0)))


def transform(grid,mcs):
    xx=[v[0] for v in mcs]
    lo,hi=xx[0],xx[-1]
    inside=below=above=0
    result=[]
    for x in grid:
        if x<lo:
            below+=1
            k=analytical_original_rate(x)
        elif x>hi:
            above+=1
            k=analytical_original_rate(x)
        else:
            inside+=1
            j=bisect.bisect_left(xx,x)
            if j==0:
                k=mcs[0][1]
            elif j==len(mcs):
                k=mcs[-1][1]
            elif x==xx[j]:
                k=mcs[j][1]
            else:
                x0,k0=mcs[j-1]
                x1,k1=mcs[j]
                k=k0+(k1-k0)*(x-x0)/(x1-x0)
        assert math.isfinite(k) and k>=0
        result.append((x,k))
    assert inside+below+above==len(grid)
    return result,{"mcs_interpolated_grid_nodes":inside,
                   "old_formula_below_MCS_grid_nodes":below,
                   "old_formula_above_MCS_grid_nodes":above,
                   "mcs_energy_min_eV":lo,"mcs_energy_max_eV":hi}


def replace_unique(s,old,new):
    assert s.count(old)==1, f"expected one source occurrence: {old[:85]}"
    return s.replace(old,new,1)


def modify_validator(path):
    """Opt-in update to *ephemeral harness only*. Original pinned git source unchanged.

    Preserve the independent required checks for the event source, two energy/particle
    RHS kernels, heavy mass closure and no reserved alias symbols.
    """
    s=path.read_text()
    check='os.environ.get("OXYGEN_RESEARCH_EI2738_MCS") == "1"'
    s=replace_unique(s,
        '"property_name = R_EI2738",',
        '("reaction_progress = R_EI2738" if '+check+' else "property_name = R_EI2738"),')
    s=replace_unique(s,
        '"expression = \'2.0e-13*exp(-5.5/te)\'",',
        '("rate_table_file = \'private_rates/EI-2738_Om.txt\'" if '+check+' else "expression = \'2.0e-13*exp(-5.5/te)\'"),')
    s=replace_unique(s,
        'if source.count("property_name = R_EI2738") != 1:',
        'if source.count(("reaction_progress = R_EI2738" if '+check+' else "property_name = R_EI2738")) != 1:')
    s=replace_unique(s,
        'variant.get("ei2738_rate_origin") != "published_maxwellian_temperature_fit_not_EEDF_integral"',
        'variant.get("ei2738_rate_origin") != (RESEARCH_MODE if '+check+' else "published_maxwellian_temperature_fit_not_EEDF_integral")')
    # RESEARCH_MODE must also be exported in the ephemeral legacy7 script.
    s=replace_unique(s,"def verify(power):", 'RESEARCH_MODE = "'+RESEARCH_MODE+'"\n\ndef verify(power):')
    path.write_text(s)
    compile(s,str(path),"exec")


def patch_overlay(power):
    path=ROOT/f"ei2738_detachment_formula_{power}w_100us_dt1000ns_overlay.i"
    s=path.read_text()
    assert s.startswith("# EI-2738 research-only: e+O- -> 2e+O(3P)")
    old_rate=re.search(r"(?ms)^  \[ei2738_rate_coefficient\]\n.*?^  \[\]\n",s)
    old_progress=re.search(r"(?ms)^  \[ei2738_detachment_progress\]\n.*?^  \[\]\n",s)
    assert old_rate and old_progress and old_rate.end()<=old_progress.start()
    assert "expression = '2.0e-13*exp(-5.5/te)'" in old_rate.group()
    assert "property_name = R_EI2738" in old_progress.group()
    assert "expression = 'k*ne*c'" in old_progress.group()
    new_material=("  [ei2738_mcs_detachment_progress]\n"
                  "    type = PhysicsElectronImpactRateMaterial\n"
                  "    rate_table_file = 'private_rates/EI-2738_Om.txt'\n"
                  "    mean_energy = mean_en_solved\n"
                  "    electron_number_density = n_e_physical\n"
                  "    target_molar_concentration = c_Om_EI2738\n"
                  "    reaction_progress = R_EI2738\n"
                  "    block = plasma\n"
                  "  []\n")
    s=s[:old_rate.start()]+new_material+s[old_progress.end():]
    assert s.count("reaction_progress = R_EI2738")==1
    assert "property_name = k_EI2738" not in s
    assert "expression = '2.0e-13*exp(-5.5/te)'" not in s
    assert s.count("expression = '-2.70*R'")==1, "retained electron-energy bookkeeping"
    assert s.count("variable = log_ne")==1 and s.count("variable = log_nm")==1
    assert s.count("functor_on_rhs = true")==2
    assert s.count("source = S_O_mass_EI2738")==1
    path.write_text(s)
    return path


def output_dir(power):
    return ROOT/f"results_rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns"


def selftest():
    mcs=parse(MCS,24)
    assert mcs[0]==(.1218,4.439e-20)
    assert mcs[-1]==(18.45,9.894e-14)
    xs=[.01,.1218,3.854,8.771,18.45,20.]
    ret,st=transform(xs,mcs)
    assert st["mcs_interpolated_grid_nodes"]==4
    assert ret[0][1]==analytical_original_rate(.01)
    assert ret[-1][1]==analytical_original_rate(20.)
    assert ret[1][1]==mcs[0][1] and ret[-2][1]==mcs[-1][1]
    assert math.isclose(ret[2][1],8.120e-15,rel_tol=1e-12)
    print("EI2738_MCS_24CASE_INTERPOLATION_NO_EXTRAPOLATION_SELFTEST_PASS",flush=True)


def install(power):
    assert power in (400,1000)
    mcs=parse(MCS,24)
    table=ROOT/"private_rates"/REFERENCE_GRID_FILE
    upstream=Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/REFERENCE_GRID_FILE
    assert digest(table)==digest(upstream), "EI943 MCS rate must already be installed"
    reference=parse(table,100)
    grid=[x for x,k in reference]
    derived,coverage=transform(grid,mcs)
    assert 20<=coverage["mcs_interpolated_grid_nodes"]<=100
    dest=ROOT/"private_rates"/LOOKUP_NAME
    assert not dest.exists(), "pre-existing EI2738 lookup must not be overwritten"
    dest.write_text("".join(f"{energy:.12e} {rate:.12e}\n" for energy,rate in derived))
    assert [x for x,k in parse(dest,100)]==grid
    overlay=patch_overlay(power)
    validator=Path(os.environ["LEGACY7"])
    modify_validator(validator)
    m=output_dir(power)/"legacy6_latest_variant.json"
    old=json.loads(m.read_text())
    assert old["chemistry_channels"]==CHANNELS
    assert old["scientific_acceptance"]=="HOLD"
    assert old["ei2738_rate_origin"]=="published_maxwellian_temperature_fit_not_EEDF_integral"
    old.update({
        "ei2738_rate_origin":RESEARCH_MODE,
        "ei2738_mcs_lookup_file":LOOKUP_NAME,
        "ei2738_mcs_lookup_sha256":digest(dest),
        "ei2738_mcs_source_table_sha256":digest(MCS),
        "ei2738_mcs_source_out_sha256":ORIGINAL_MCS_OUT_SHA256,
        "ei2738_original_rate_origin":"published_maxwellian_temperature_fit_not_EEDF_integral",
        "ei2738_mcs_provisional_mapping":True,
        "ei2738_mcs_replaced_grid_nodes":coverage["mcs_interpolated_grid_nodes"],
        "ei2738_mcs_model_energy_loss_eV":2.70,
        "ei2738_scientific_status":"HOLD",
    })
    m.write_text(json.dumps(old,indent=2,sort_keys=True)+"\n")
    audit={
        "power_w":power,
        "source_label":"O- Detachment (MCS); provisional EI2738 mapping",
        "mcs_out_sha256":ORIGINAL_MCS_OUT_SHA256,
        "mcs_24case_table_sha256":digest(MCS),
        "derived_100point_rate_sha256":digest(dest),
        "reference_grid_sha256":digest(table),
        "lookup_filename":LOOKUP_NAME,
        "energy_axis":"mean_energy_eV",
        "rate_units":"m3/s",
        "energy_loss_eV":2.70,
        "out_of_mcs_domain":"retained original EI2738 analytic fit; NO MCS extrapolation",
        "sci_status":"HOLD",
        **coverage,
    }
    (output_dir(power)/"mcs_ei2738_swap_audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
    os.environ[FLAG]="1"
    verify(power)
    print("EI2738_MCS_NEW_LOOKUP_AND_EPHEMERAL_VALIDATOR_PASS",power,coverage,flush=True)


def verify(power):
    audit=json.loads((output_dir(power)/"mcs_ei2738_swap_audit.json").read_text())
    manifest=json.loads((output_dir(power)/"legacy6_latest_variant.json").read_text())
    assert audit["power_w"]==power and manifest["scientific_acceptance"]=="HOLD"
    assert manifest["chemistry_channels"]==CHANNELS and manifest["ei2738_rate_origin"]==RESEARCH_MODE
    assert audit["mcs_out_sha256"]==ORIGINAL_MCS_OUT_SHA256
    assert audit["mcs_24case_table_sha256"]==digest(MCS)
    assert manifest["ei2738_mcs_source_table_sha256"]==audit["mcs_24case_table_sha256"]
    dest=ROOT/"private_rates"/LOOKUP_NAME
    assert digest(dest)==audit["derived_100point_rate_sha256"]==manifest["ei2738_mcs_lookup_sha256"]
    ref=ROOT/"private_rates"/REFERENCE_GRID_FILE
    grid=[x for x,k in parse(ref,100)]
    expected,cover=transform(grid,parse(MCS,24))
    values=parse(dest,100)
    assert values==[(float(f"{x:.12e}"),float(f"{v:.12e}")) for x,v in expected]
    assert audit["mcs_interpolated_grid_nodes"]==cover["mcs_interpolated_grid_nodes"]
    assert len(values)==100
    src=(ROOT/f"ei2738_detachment_formula_{power}w_100us_dt1000ns_overlay.i").read_text()
    assert src.count("rate_table_file = 'private_rates/EI-2738_Om.txt'")==1
    assert src.count("reaction_progress = R_EI2738")==1
    assert src.count("expression = '-2.70*R'")==1
    assert src.count("functor_on_rhs = true")==2
    assert not any(x in src for x in ("R_H23","R_H05","R_EI2058","R_EI2259","R_EI2072","R_EI2074"))
    assert manifest["ei943_mcs_source_out_sha256"]==ORIGINAL_MCS_OUT_SHA256
    assert manifest["ei943_rate_mode"].startswith("MCS_")
    print("EI2738_MCS_SOURCE_AND_100POINT_DERIVATION_PASS",power,flush=True)


def archive(power):
    verify(power)
    path=output_dir(power)/"legacy6_restart_100000ns_manifest.json"
    j=json.loads(path.read_text())
    audit=json.loads((output_dir(power)/"mcs_ei2738_swap_audit.json").read_text())
    assert j["verified_full_native_100us_checkpoint"] and j["native_endpoint_s"]==1e-4
    assert j["scientific_acceptance"]=="HOLD"
    assert j["chemistry_channels"]==CHANNELS
    assert j["ei943_mcs_swap_audit"]["mcs_source_out_sha256"]==ORIGINAL_MCS_OUT_SHA256
    j["ei2738_mcs_swap_audit"]=audit
    j["ei2738_scientific_status"]="HOLD"
    j["ei2738_mcs_lookup_sha256"]=audit["derived_100point_rate_sha256"]
    path.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    print("EI2738_MCS_100US_ARCHIVE_MANIFEST_PASS",power,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","install","verify","archive"))
    p.add_argument("--power-w",type=int)
    args=p.parse_args()
    if args.action=="selftest":selftest()
    else:
        assert args.power_w in (400,1000)
        {"install":install,"verify":verify,"archive":archive}[args.action](args.power_w)
