#!/usr/bin/env python3
"""Replace only EI-943 rate by MCS O(1D)->O data in an isolated 13ch run.

Uses authentic private EI943 100-row abscissae; at energies within the 24 MCS
cases, linearly interpolate MCS rate. Outside the MCS data range, preserve
the original (private) EI943 rate *at that grid node*: NO MCS extrapolation.
This is a controlled hybrid outside data coverage, not a fully MCS-based
kinetic model. Never upload rate-table contents or protected raw rates.
"""
from __future__ import annotations
import argparse
import bisect
import hashlib
import json
import math
import os
from pathlib import Path

RATE = "EI-943_O_1D.txt"
OTHER_RATES = ["EI-407_O2_X.txt","EI-417_O2_X.txt","EI-935_O_3P.txt"]
ORIGINAL_MCS_OUT_SHA256 = "d3db627a2d97b2bcc355c2f241b7bb231f49463cd0bb3ef6b13383166802ab08"
CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
MCS = Path("_legacy6_control/experiments/Issue395_powered_chemistry_ladder/ei943_mcs_24case_mean_energy_rate_m3_s.txt")


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def parse(path: Path, count: int):
    assert path.is_file(), "missing rate file: "+str(path)
    out=[]
    for line in path.read_text().splitlines():
        line=line.split("#",1)[0].strip()
        if not line:
            continue
        fields=line.split()
        assert len(fields)==2, "expected two-column rate lookup"
        x,y=map(float,fields)
        assert math.isfinite(x) and math.isfinite(y) and x>0 and y>=0
        if out:
            assert x>out[-1][0], "non-monotonic rate grid"
        out.append((x,y))
    assert len(out)==count, f"expected {count} rows, found {len(out)}"
    return out


def blended(original, mcs):
    xx=[x for x,_ in mcs]
    lo,hi=xx[0],xx[-1]
    replaced=0
    outside_low=0
    outside_high=0
    out=[]
    for x,old_y in original:
        if x<lo:
            outside_low+=1
            y=old_y
        elif x>hi:
            outside_high+=1
            y=old_y
        else:
            replaced+=1
            k=bisect.bisect_left(xx,x)
            if k==0:
                y=mcs[0][1]
            elif k==len(mcs):
                y=mcs[-1][1]
            elif x==xx[k]:
                y=mcs[k][1]
            else:
                x0,y0=mcs[k-1]
                x1,y1=mcs[k]
                y=y0+(y1-y0)*(x-x0)/(x1-x0)
        assert math.isfinite(y) and y>=0
        out.append((x,y))
    return out,{"points_replaced_by_mcs":replaced,
                "points_retaining_original_below_mcs":outside_low,
                "points_retaining_original_above_mcs":outside_high,
                "mcs_energy_domain_eV":[lo,hi]}


def result(power):
    return CHEM/f"results_rf_elastic_diss_ion_ei20_ei01_{power}w_adjacent_sheath_wall_closed_100us_dt1000ns"


def install(power: int):
    assert power in (400,1000)
    mcs=parse(MCS,24)
    assert mcs[0]==(.1218,1.276e-16) and mcs[-1]==(18.45,2.958e-15)
    src=Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/RATE
    dst=CHEM/"private_rates"/RATE
    original=parse(src,100)
    assert parse(dst,100)==original
    src_sha=digest(src)
    assert digest(dst)==src_sha
    originals={}
    for name in OTHER_RATES:
        ps=Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/name
        pd=CHEM/"private_rates"/name
        assert ps.exists() and pd.exists() and digest(ps)==digest(pd)
        originals[name]=digest(ps)
    derived,coverage=blended(original,mcs)
    assert 20<=coverage["points_replaced_by_mcs"]<=100, "MCS domain barely covers private grid"
    assert len(derived)==100
    assert [x for x,_ in derived]==[x for x,_ in original], "MCS changed lookup abscissa"
    assert any(abs(a[1]-b[1])>max(a[1],b[1])*1e-10 for a,b in zip(derived,original)), "MCS swap made no change"
    # Explicitly verify every out-of-domain coefficient remains *unchanged*.
    for (x,old),(new_x,new_y) in zip(original,derived):
        assert x==new_x
        if x<mcs[0][0] or x>mcs[-1][0]:
            assert old==new_y
    output="".join(f"{x:.12e} {y:.12e}\n" for x,y in derived)
    # Check both original rate packages only inside ephemeral CI workspaces.
    src.write_text(output)
    dst.write_text(output)
    assert parse(src,100)==parse(dst,100)
    assert [x for x,_ in parse(dst,100)]==[x for x,_ in original]
    new_sha=digest(dst)
    assert new_sha==digest(src) and new_sha!=src_sha
    for name,original_hash in originals.items():
        assert digest(CHEM/"private_rates"/name)==original_hash
        assert digest(Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/name)==original_hash
    manifest_path=result(power)/"legacy6_latest_variant.json"
    j=json.loads(manifest_path.read_text())
    assert "H23" not in j["chemistry_channels"]
    assert j["chemistry_channels"]==["EI-01","EI-02","DISS-G","EI-16","EI-17","EI-20","EI-2738","EI-407","EI-417","EI-935","EI-943","H24","H25"]
    assert j["scientific_acceptance"]=="HOLD"
    assert j["ei943_lookup_sha256"]==src_sha
    for channel,name in [("ei407",OTHER_RATES[0]),("ei417",OTHER_RATES[1]),("ei935",OTHER_RATES[2])]:
        assert j[channel+"_lookup_sha256"]==originals[name]
    j.update({
        "ei943_lookup_sha256":new_sha,
        "ei943_original_private_lookup_sha256":src_sha,
        "ei943_rate_source":"MCS(1).OUT O(1D) > O RATE CONST (CC/S); 24-case interpolation",
        "ei943_rate_mode":"MCS_linear_in_covered_mean_energy_domain_original_lookup_outside_no_extrapolation",
        "ei943_mcs_source_out_sha256":ORIGINAL_MCS_OUT_SHA256,
        "ei943_mcs_source_table_sha256":digest(MCS),
        "ei943_mcs_energy_domain_eV":coverage["mcs_energy_domain_eV"],
        "ei943_mcs_replaced_grid_nodes":coverage["points_replaced_by_mcs"],
        "ei943_mcs_original_low_grid_nodes":coverage["points_retaining_original_below_mcs"],
        "ei943_mcs_original_high_grid_nodes":coverage["points_retaining_original_above_mcs"],
        "ei943_mcs_scientific_status":"HOLD",
    })
    manifest_path.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    audit={
        "power_W":power,"research_mode":"single_EI943_rate_swap_no_other_reaction_changes",
        "original_lookup_sha256":src_sha,"derived_lookup_sha256":new_sha,
        "mcs_source_out_sha256":ORIGINAL_MCS_OUT_SHA256,
        "mcs_table_sha256":digest(MCS),
        "other_rates_sha256":originals,
        "original_grid_points":100,"source_case_points":24,
        **coverage,
        "extrapolation":"NONE; out-of-MCS-domain original EI943 private rate unchanged",
        "mean_energy_axis":"eV",
        "units":"m3/s",
        "scientific_acceptance":"HOLD",
    }
    (result(power)/"mcs_ei943_swap_audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
    verify(power)
    print("EI943_MCS_SINGLE_RATE_SWAP_INSTALLED",power,new_sha,coverage,flush=True)


def verify(power: int):
    mcs=parse(MCS,24)
    dst=CHEM/"private_rates"/RATE
    src=Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/RATE
    table=parse(dst,100)
    assert parse(src,100)==table
    audit=json.loads((result(power)/"mcs_ei943_swap_audit.json").read_text())
    manifest=json.loads((result(power)/"legacy6_latest_variant.json").read_text())
    assert audit["power_W"]==power
    assert audit["mcs_source_out_sha256"]==ORIGINAL_MCS_OUT_SHA256
    assert audit["mcs_table_sha256"]==digest(MCS)
    assert audit["derived_lookup_sha256"]==digest(dst)==digest(src)
    assert manifest["ei943_lookup_sha256"]==audit["derived_lookup_sha256"]
    assert manifest["ei943_original_private_lookup_sha256"]==audit["original_lookup_sha256"]
    assert manifest["ei943_mcs_replaced_grid_nodes"]==audit["points_replaced_by_mcs"]
    assert manifest["scientific_acceptance"]=="HOLD"
    assert manifest["ei943_energy_loss_eV"]==-1.967
    assert len(manifest["chemistry_channels"])==13 and "H23" not in manifest["chemistry_channels"]
    for name,h in audit["other_rates_sha256"].items():
        assert digest(CHEM/"private_rates"/name)==h
        assert digest(Path(os.environ["OXYGEN_RESEARCH_RATE_DIR"])/name)==h
    # No original-private coefficient is stored in public audit.
    assert "private_rates" not in str(audit)
    print("EI943_MCS_LOOKUP_PROVENANCE_VERIFIED",power,audit["points_replaced_by_mcs"],flush=True)


def archive(power: int):
    verify(power)
    p=result(power)/"legacy6_restart_100000ns_manifest.json"
    j=json.loads(p.read_text())
    audit=json.loads((result(power)/"mcs_ei943_swap_audit.json").read_text())
    assert j["verified_full_native_100us_checkpoint"]
    assert j["native_endpoint_s"]==1e-4 and j["scientific_acceptance"]=="HOLD"
    assert j["ei943_lookup_sha256"]==j["ei943_recovery_rate_sha256"]==audit["derived_lookup_sha256"]
    j["ei943_mcs_swap_audit"]=audit
    j["ei943_mcs_original_private_lookup_sha256"]=audit["original_lookup_sha256"]
    j["ei943_mcs_scientific_status"]="HOLD"
    p.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    print("EI943_MCS_100US_NATIVE_ENDPOINT_PROVENANCE_ARCHIVED",power,flush=True)


def self_test():
    mcs=parse(MCS,24)
    assert mcs[0]==(.1218,1.276e-16) and mcs[-1]==(18.45,2.958e-15)
    assert all(k>=0 for e,k in mcs)
    synthetic=[(.01,1e-15),(.1218,1e-15),(3.854,1e-15),(6.0,1e-15),(18.45,1e-15),(20.0,1e-15)]
    merged,counts=blended(synthetic,mcs)
    assert counts["points_replaced_by_mcs"]==4
    assert merged[0]==synthetic[0] and merged[-1]==synthetic[-1]
    assert merged[1][1]==mcs[0][1] and merged[-2][1]==mcs[-1][1]
    assert abs(merged[2][1]-3.357e-15)<1e-25
    print("EI943_MCS_INTERPOLATION_AND_NO_EXTRAPOLATION_SELF_TEST_PASS",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["self-test","install","verify","archive"])
    parser.add_argument("--power-w",type=int)
    args=parser.parse_args()
    if args.action=="self-test":
        self_test()
    else:
        assert args.power_w in (400,1000)
        {"install":install,"verify":verify,"archive":archive}[args.action](args.power_w)
