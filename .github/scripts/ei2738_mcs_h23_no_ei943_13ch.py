#!/usr/bin/env python3
"""Preparation-only MCS EI2738 substitution for H23-IN / EI943-OUT 13 channels.

The old EI2738 analytical Maxwellian rate is replaced on the original 100-node
mean-energy grid with 24-case MCS O- detachment data (provisional identity).
Outside the measured MCS domain use the *old analytical rate*, not MCS
extrapolation. Rate is always interpreted in physical m3/s, then converted
to PhysicsElectronImpactRateMaterial's required raw units m3/(mol s) by N_A.

The original EI943 private lookup is used ONLY to capture its mean-energy
abscissa BEFORE the no-EI943 preparation deletes that lookup. No private rate
values are copied or published. This script modifies only CI working copies.
No native run is triggered by any command in this script.
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
import shutil

ROOT=Path("experiments/Issue395_powered_chemistry_ladder")
MCS=Path("_legacy6_control/experiments/Issue395_powered_chemistry_ladder/ei2738_mcs_24case_mean_energy_rate_m3_s.txt")
EI943_ORIGINAL="EI-943_O_1D.txt"
EI2738_LOOKUP="EI-2738_Om_MCS.txt"
REFERENCE_GRID="ei2738_mcs_reference_energy_grid_100.txt"
AUDIT_NAME="mcs_ei2738_swap_audit.json"
SAFE_LOOKUP="ei2738_mcs_derived_lookup_100pt.txt"
FLAG="OXYGEN_RESEARCH_EI2738_MCS"
ORIGINAL_MCS_OUT_SHA256="d3db627a2d97b2bcc355c2f241b7bb231f49463cd0bb3ef6b13383166802ab08"
ORIGIN="MCS_Ominus_detachment_24case_mean_energy_lookup_with_analytic_fit_tails_provisional"
OLD_ORIGIN="published_maxwellian_temperature_fit_not_EEDF_integral"
N_A=6.02214076e23
ENERGY_LOSS_EV=2.70
CHANNELS=["EI-01","EI-02","DISS-G","EI-16","EI-17","EI-20",
          "EI-2738","EI-407","EI-417","EI-935","H24","H25","H23"]
EXPECTED_VARIANT="LEGACY8_EI417_EI935_H24_H25_H23_NO_EI943_IMPACT_ABLATION_HOLD"


def result(power:int)->Path:
    assert power in (400,1000)
    return ROOT/f"results_rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns"


def digest(p:Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def parse_mcs():
    rows=[]
    for line in MCS.read_text().splitlines():
        line=line.split("#",1)[0].strip()
        if not line: continue
        x,k=map(float,line.split())
        assert math.isfinite(x) and math.isfinite(k) and x>0 and k>=0
        if rows: assert x>rows[-1][0]
        rows.append((x,k))
    assert len(rows)==24
    assert rows[0]==(.1218,4.439e-20)
    assert rows[-1]==(18.45,9.894e-14)
    return rows


def parse_lookup(p:Path,points=100):
    rows=[]
    for line in p.read_text().splitlines():
        line=line.split("#",1)[0].strip()
        if not line: continue
        vals=line.split()
        assert len(vals)==2, "lookup must contain energy and rate"
        raw_x,raw_k=vals
        x,k=float(raw_x),float(raw_k)
        assert math.isfinite(x) and math.isfinite(k) and x>0 and k>=0
        if rows: assert x>rows[-1][0], "non-monotonic grid"
        rows.append((raw_x,x,k))
    assert len(rows)==points, f"expected {points} grid nodes, found {len(rows)}"
    return rows


def parse_grid(p:Path):
    rows=[]
    for line in p.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith("#"): continue
        x=float(line)
        assert math.isfinite(x) and x>0
        if rows: assert x>rows[-1][1]
        rows.append((line,x))
    assert len(rows)==100
    return rows


def analytical_rate(x):
    assert x>0
    return 2.0e-13*math.exp(-5.5/((2.0/3.0)*x))


def rate_physical(x,mcs):
    xx=[r[0] for r in mcs]
    if x<xx[0] or x>xx[-1]:
        return analytical_rate(x),False
    i=bisect.bisect_left(xx,x)
    if i<len(xx) and x==xx[i]:
        return mcs[i][1],True
    if i==0: return mcs[0][1],True
    if i==len(xx): return mcs[-1][1],True
    x0,k0=mcs[i-1]
    x1,k1=mcs[i]
    return k0+(k1-k0)*(x-x0)/(x1-x0),True


def sample_points(grid,mcs):
    counts={"in_MCS":0,"analytic_below":0,"analytic_above":0}
    derived=[]
    for xtok,x in grid:
        rate,in_mcs=rate_physical(x,mcs)
        if in_mcs: counts["in_MCS"]+=1
        elif x<mcs[0][0]: counts["analytic_below"]+=1
        else: counts["analytic_above"]+=1
        k_raw=rate*N_A
        assert math.isfinite(k_raw) and k_raw>=0
        # Original x token is preserved exactly to avoid float roundtrip drift.
        derived.append((xtok,x,rate,k_raw))
    assert sum(counts.values())==len(grid)
    assert counts["in_MCS"]>=20, "too few MCS-covered original grid nodes"
    return derived,counts


def capture_grid(power):
    """Run while exact original 14ch parent and private EI943 lookup still exist."""
    path=ROOT/"private_rates"/EI943_ORIGINAL
    src=Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/EI943_ORIGINAL
    assert path.is_file() and src.is_file()
    assert digest(path)==digest(src), "original EI943 private rate mismatch"
    original=parse_lookup(path)
    out=result(power)
    manifest=json.loads((out/"legacy6_latest_variant.json").read_text())
    assert manifest["chemistry_channels"]==CHANNELS[:10]+["EI-943","H24","H25","H23"]
    assert manifest["ei943_lookup_sha256"]==digest(path)
    grid=out/REFERENCE_GRID
    assert not grid.exists()
    grid.write_text("".join(token+"\n" for token,x,k in original))
    assert [v[1] for v in parse_grid(grid)]==[v[1] for v in original]
    (out/"ei2738_mcs_reference_grid_provenance.json").write_text(json.dumps({
        "power_w":power,
        "original_ei943_lookup_sha256":digest(path),
        "reference_grid_sha256":digest(grid),
        "grid_nodes":100,
        "contains_private_rate_values":False,
        "capture_before_EI943_ablation":True,
        "scientific_acceptance":"HOLD",
    },indent=2,sort_keys=True)+"\n")
    print("EI2738_MCS_CAPTURED_REFERENCE_GRID_NO_PRIVATE_RATES_PASS",power,flush=True)


def replace_once(s,old,new):
    assert s.count(old)==1, "source identity mismatch: "+old[:90]
    return s.replace(old,new,1)


def patch_legacy7_validator():
    """Only the ephemeral research harness, never the pinned Physics repository."""
    path=Path(os.environ["LEGACY7"])
    s=path.read_text()
    switch='os.environ.get("OXYGEN_RESEARCH_EI2738_MCS") == "1"'
    s=replace_once(s,
        '"property_name = R_EI2738",',
        '("reaction_progress = R_EI2738" if '+switch+' else "property_name = R_EI2738"),')
    s=replace_once(s,
        '"expression = \'2.0e-13*exp(-5.5/te)\'",',
        '("rate_table_file = \'private_rates/EI-2738_Om_MCS.txt\'" if '+switch+' else "expression = \'2.0e-13*exp(-5.5/te)\'"),')
    s=replace_once(s,
        'if source.count("property_name = R_EI2738") != 1:',
        'if source.count(("reaction_progress = R_EI2738" if '+switch+' else "property_name = R_EI2738")) != 1:')
    s=replace_once(s,
        'variant.get("ei2738_rate_origin") != "published_maxwellian_temperature_fit_not_EEDF_integral"',
        'variant.get("ei2738_rate_origin") != ("'+ORIGIN+'" if '+switch+' else "published_maxwellian_temperature_fit_not_EEDF_integral")')
    path.write_text(s)
    compile(s,str(path),"exec")


def patch_overlay(power):
    p=ROOT/f"ei2738_detachment_formula_{power}w_100us_dt1000ns_overlay.i"
    s=p.read_text()
    assert s.startswith("# EI-2738 research-only: e+O- -> 2e+O(3P)")
    a=re.search(r"(?ms)^  \[ei2738_rate_coefficient\]\n.*?^  \[\]\n",s)
    b=re.search(r"(?ms)^  \[ei2738_detachment_progress\]\n.*?^  \[\]\n",s)
    assert a and b and a.end()<=b.start()
    assert "expression = '2.0e-13*exp(-5.5/te)'" in a.group()
    assert "property_name = R_EI2738" in b.group()
    assert "expression = 'k*ne*c'" in b.group()
    new='''  [ei2738_mcs_detachment_progress]
    type = PhysicsElectronImpactRateMaterial
    rate_table_file = 'private_rates/EI-2738_Om_MCS.txt'
    mean_energy = mean_en_solved
    electron_number_density = n_e_physical
    target_molar_concentration = c_Om_EI2738
    reaction_progress = R_EI2738
    block = plasma
  []
'''
    s=s[:a.start()]+new+s[b.end():]
    assert s.count("reaction_progress = R_EI2738")==1
    assert "property_name = k_EI2738" not in s
    assert "property_name = R_EI2738" not in s
    assert "expression = '2.0e-13*exp(-5.5/te)'" not in s
    assert s.count("expression = '-2.70*R'")==1
    assert s.count("variable = log_ne")==1 and s.count("variable = log_nm")==1
    assert s.count("functor_on_rhs = true")==2
    assert s.count("source = S_O_mass_EI2738")==1
    p.write_text(s)
    return p


def install(power):
    """Run AFTER no-EI943 ablation prepare, BEFORE its subsequent verify."""
    assert_flag=os.environ.get("OXYGEN_RESEARCH_EI2738_FORMULA")=="1"
    assert assert_flag, "old formula must be parent kinetic baseline"
    out=result(power)
    manifest_path=out/"legacy6_latest_variant.json"
    m=json.loads(manifest_path.read_text())
    assert m["chemistry_channels"]==CHANNELS
    assert m["variant"]==EXPECTED_VARIANT
    assert m["ei943_ablation"]=="FULLY_EXCLUDED_FROM_CHECK_AND_SOLVE_ARGV_NOT_ZERO_RATE"
    assert m["ei2738_rate_origin"]==OLD_ORIGIN
    assert m["scientific_acceptance"]=="HOLD"
    assert not (ROOT/"private_rates"/EI943_ORIGINAL).exists(), "EI943 must be removed"
    assert not (ROOT/f"ei943_atomic_superelastic_{power}w_100us_dt1000ns_overlay.i").exists()
    grid_path=out/REFERENCE_GRID
    assert grid_path.exists()
    prov=json.loads((out/"ei2738_mcs_reference_grid_provenance.json").read_text())
    assert digest(grid_path)==prov["reference_grid_sha256"]
    assert m["ei943_ablation_parent_private_rate_sha256"]==prov["original_ei943_lookup_sha256"]
    mcs=parse_mcs()
    sampled,counts=sample_points(parse_grid(grid_path),mcs)
    target=ROOT/"private_rates"/EI2738_LOOKUP
    assert not target.exists(), "do not overwrite existing EI2738 lookup"
    target.write_text("".join(f"{xtok} {kraw:.16e}\n" for xtok,x,k,kraw in sampled))
    actual=parse_lookup(target)
    assert [v[0] for v in actual]==[v[0] for v in sampled], "abscissa token drift"
    assert all(math.isclose(actual[i][2],sampled[i][3],rel_tol=1e-14,abs_tol=0)
               for i in range(100))
    patch_overlay(power)
    patch_legacy7_validator()
    audit={
        "power_w":power,
        "source_label":"MCS(1).OUT 24 CASE O- Detachment; provisional EI-2738 mapping",
        "mcs_source_raw_out_sha256":ORIGINAL_MCS_OUT_SHA256,
        "mcs_24case_table_sha256":digest(MCS),
        "mcs_energy_range_eV":[mcs[0][0],mcs[-1][0]],
        "energy_grid_sha256":digest(grid_path),
        "energy_grid_node_count":100,
        "original_ei943_private_rate_values_copied":False,
        "derived_table_sha256":digest(target),
        "derived_table_file":EI2738_LOOKUP,
        "physical_source_rate_units":"m3/s",
        "native_lookup_rate_units":"m3/(mol s)",
        "native_lookup_scale_from_source_multiply_by_N_A":N_A,
        "PhysicsElectronImpactRateMaterial_progress":"k_raw*(n_e/N_A)*c_Ominus",
        "MCS_stoichiometry_match_verified":False,
        "model_energy_loss_eV":ENERGY_LOSS_EV,
        "out_of_source_domain":"original analytical fit k=2e-13 exp(-5.5/(2*mean_energy/3))",
        "scientific_acceptance":"HOLD",
        **counts,
    }
    (out/AUDIT_NAME).write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
    m.update({
        "ei2738_rate_origin":ORIGIN,
        "ei2738_original_rate_origin":OLD_ORIGIN,
        "ei2738_mcs_lookup_file":EI2738_LOOKUP,
        "ei2738_mcs_lookup_sha256":digest(target),
        "ei2738_mcs_source_table_sha256":digest(MCS),
        "ei2738_mcs_source_out_sha256":ORIGINAL_MCS_OUT_SHA256,
        "ei2738_mcs_mapping_provisional":True,
        "ei2738_mcs_native_rate_unit_conversion":"m3/s_to_m3/(mol s): multiply by N_A",
        "ei2738_mcs_covered_grid_nodes":counts["in_MCS"],
        "ei2738_model_energy_loss_eV":ENERGY_LOSS_EV,
        "ei2738_scientific_status":"HOLD",
        "rate_origin":"original six public rates, EI2738 MCS provisional, other parent rates unchanged",
    })
    manifest_path.write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
    os.environ[FLAG]="1"
    verify(power)
    print("H23_NO_EI943_EI2738_MCS_NATIVE_LOOKUP_PREPARED_PASS",power,counts,flush=True)


def verify(power):
    assert os.environ.get(FLAG)=="1"
    out=result(power)
    m=json.loads((out/"legacy6_latest_variant.json").read_text())
    a=json.loads((out/AUDIT_NAME).read_text())
    assert m["chemistry_channels"]==CHANNELS
    assert m["variant"]==EXPECTED_VARIANT
    assert m["ei2738_rate_origin"]==ORIGIN
    assert m["scientific_acceptance"]=="HOLD"
    assert "EI-943" not in m["chemistry_channels"] and "H23" in m["chemistry_channels"]
    assert a["mcs_source_raw_out_sha256"]==ORIGINAL_MCS_OUT_SHA256
    assert a["mcs_24case_table_sha256"]==digest(MCS)
    assert a["derived_table_sha256"]==m["ei2738_mcs_lookup_sha256"]
    assert a["native_lookup_scale_from_source_multiply_by_N_A"]==N_A
    assert a["native_lookup_rate_units"]=="m3/(mol s)"
    assert a["scientific_acceptance"]=="HOLD"
    assert a["model_energy_loss_eV"]==ENERGY_LOSS_EV
    grid=parse_grid(out/REFERENCE_GRID)
    source=parse_mcs()
    generated,coverage=sample_points(grid,source)
    table=parse_lookup(ROOT/"private_rates"/EI2738_LOOKUP)
    assert digest(ROOT/"private_rates"/EI2738_LOOKUP)==a["derived_table_sha256"]
    assert [v[0] for v in table]==[v[0] for v in generated]
    assert all(math.isclose(v[2],s[3],rel_tol=1e-13,abs_tol=0) for v,s in zip(table,generated))
    for i,(tok,x,kraw) in enumerate(table):
        # Demonstrate dimensional consistency of the native material with
        # the physical reaction rate k_phys*n_e*c_target, at n_e=1e16, c=1.
        n_e,c_target=1e16,1.0
        actual=kraw*(n_e/N_A)*c_target
        expected=generated[i][2]*n_e*c_target
        assert math.isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-20)
    assert a["in_MCS"]==coverage["in_MCS"]
    p=ROOT/f"ei2738_detachment_formula_{power}w_100us_dt1000ns_overlay.i"
    s=p.read_text()
    assert s.count("type = PhysicsElectronImpactRateMaterial")==1
    assert s.count(f"rate_table_file = 'private_rates/{EI2738_LOOKUP}'")==1
    assert s.count("mean_energy = mean_en_solved")==1
    assert s.count("reaction_progress = R_EI2738")==1
    assert s.count("expression = '-2.70*R'")==1
    assert s.count("variable = log_ne")==1 and s.count("variable = log_nm")==1
    assert s.count("functor_on_rhs = true")==2
    assert s.count("source = S_O_mass_EI2738")==1
    assert not any(x in s for x in ("R_EI943","R_H05","R_EI2058","R_EI2259","R_EI2072","R_EI2074"))
    assert not (ROOT/"private_rates"/EI943_ORIGINAL).exists()
    assert not (ROOT/f"ei943_atomic_superelastic_{power}w_100us_dt1000ns_overlay.i").exists()
    assert (out/"no_ei943_ablation_audit.json").exists()
    print("H23_NO_EI943_EI2738_MCS_SOURCE_AND_RATE_UNITS_VERIFIED",power,flush=True)


def archive(power):
    verify(power)
    out=result(power)
    target=ROOT/"private_rates"/EI2738_LOOKUP
    archived=out/SAFE_LOOKUP
    assert not archived.exists()
    shutil.copyfile(target,archived)
    assert digest(archived)==digest(target)
    manifest_path=out/"legacy6_restart_100000ns_manifest.json"
    m=json.loads(manifest_path.read_text())
    audit=json.loads((out/AUDIT_NAME).read_text())
    assert m["verified_full_native_100us_checkpoint"] and m["native_endpoint_s"]==1e-4
    assert m["scientific_acceptance"]=="HOLD" and m["chemistry_channels"]==CHANNELS
    assert not any("ei943" in x["path"].lower() for x in m["inventory"]["inputs"])
    m.update({
        "ei2738_mcs_swap_audit":audit,
        "ei2738_mcs_derived_rate_sha256":digest(archived),
        "ei2738_mcs_derived_rate_recovery_artifact":SAFE_LOOKUP,
        "ei2738_mcs_recovery_private_rate_target":f"private_rates/{EI2738_LOOKUP}",
        "ei2738_rate_origin":ORIGIN,
        "ei2738_scientific_status":"HOLD",
        "ei943_recovery_rate_required":False,
        "ei943_recovery_overlay_required":False,
    })
    manifest_path.write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
    print("H23_NO_EI943_EI2738_MCS_100US_MANIFEST_PASS",power,flush=True)


def self_test():
    mcs=parse_mcs()
    assert len(mcs)==24
    for x in (.01,.1218,3.854,8.771,18.45,20.0):
        rate,inside=rate_physical(x,mcs)
        assert math.isfinite(rate) and rate>=0
        if x in (.01,20.0):
            assert not inside and rate==analytical_rate(x)
        else:
            assert inside
        k_raw=rate*N_A
        ne,c=1e16,2e-4
        assert math.isclose(k_raw*(ne/N_A)*c,rate*ne*c,rel_tol=1e-14,abs_tol=1e-20)
    rate,_=rate_physical(3.854,mcs)
    assert math.isclose(rate,8.120e-15,rel_tol=1e-13)
    assert len(CHANNELS)==len(set(CHANNELS))==13
    assert "H23" in CHANNELS and "EI-943" not in CHANNELS
    print("H23_NO_EI943_EI2738_MCS_UNITS_AND_INTERPOLATION_SELFTEST_PASS",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["self-test","capture-grid","install","verify","archive"])
    p.add_argument("--power-w",type=int)
    args=p.parse_args()
    if args.action=="self-test":self_test()
    else:
        assert args.power_w in (400,1000)
        {"capture-grid":capture_grid,"install":install,"verify":verify,
         "archive":archive}[args.action](args.power_w)
