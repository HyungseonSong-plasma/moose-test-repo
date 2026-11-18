#!/usr/bin/env python3
"""P6-D2/D4: fail-closed source identity, data authority and single-owner contract.

Standard-library-only static source proof. No Native, no EI private bytes, no P3/P4.
A static PASS establishes the CONTRACT, not that PR684 currently satisfies D4 Native.
"""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess

HEAD = "74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f"
PR684 = "3e48a0651ac53ec32e34b4b31e44098ffad80e1c"
HISTORY = "29d1acc6ef7969908b86719e4b95c73a1565136d"
LOOKUP100 = "994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387"
LOOKUP42 = "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
S6JSON = {
    "417": ("ed99493d992c71b30e7a4120646af388894032d262b9af5bf299522629fe24ef",
            "EI-417"),
    "941": ("2a7d6b191eddf6a92a6bcf74fc818ade8f30836fdd857dc70516f3aa57fa5dde",
            "EI-941"),
}
ION = {"O2p":1,"Om":-1,"Op":1}
REQUIRED_REACTIONS = {"EI-02","EI-17","EI-415","EI-401","EI-407","EI-2069","H25"}
TRANSPORT_MANUAL = (
    "electron_transport", "O2p_species_transport_alias",
    "Om_species_transport_alias", "Op_species_transport_alias")
LOOKUP_ORIGINAL_PATH = "experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
LOOKUP_PREPARED_PATH = ".github/oxygen25_eedf/initial_mixture_23xsec_transport.txt"
JSON_DIR = "experiments/Issue402_plasma_dsl_g1/chemistry"

def sha(data):
    return hashlib.sha256(data).hexdigest()

def reject(condition, tag):
    if not condition:
        raise AssertionError(tag)

def git_head(directory):
    return subprocess.check_output(
        ["git","-C",str(directory),"rev-parse","HEAD"], text=True).strip()

def overlay(source):
    tree = ast.parse(source)
    values = [ast.literal_eval(node.value) for node in tree.body
              if isinstance(node, ast.Assign) and
              any(isinstance(x, ast.Name) and x.id == "OVERLAY" for x in node.targets)]
    reject(len(values)==1 and isinstance(values[0],str),
           "OVERLAY_NOT_ONE_LITERAL")
    return values[0]

def parsed_rows(data, count):
    lines=[s for s in data.decode("utf-8").splitlines() if s.strip()]
    reject(len(lines)==count, "LOOKUP_WRONG_ROW_COUNT")
    triples=[]
    for line in lines:
        values=line.split()
        reject(len(values)==3, "LOOKUP_NOT_THREE_COLUMNS")
        triples.append(tuple(float(k) for k in values))
    reject(all(x[0]<y[0] for x,y in zip(triples,triples[1:])),
           "LOOKUP_NONMONOTONIC_AXIS")
    return {"rows":len(lines),"energy_start":triples[0][0],
            "energy_end":triples[-1][0]}

def static_contract(s):
    contract=s["contract"]
    h100=s["lookup100"]
    h42=s["lookup42"]
    reject(sha(h100)==LOOKUP100,"ORIGINAL_100_SHA_DRIFT")
    reject(sha(h42)==LOOKUP42,"PREPARED_42_SHA_DRIFT")
    r100=parsed_rows(h100,100)
    r42=parsed_rows(h42,42)
    reject(sha(h100)!=sha(h42) and r100["energy_start"]!=r42["energy_start"],
           "LOOKUP_AUTHORITY_COLLAPSED")
    reject(contract["modes"]["historical_100"]["sha256"]==LOOKUP100 and
           contract["modes"]["public_prepared_42"]["sha256"]==LOOKUP42 and
           contract["modes"]["newonly_42"]["table_sha256"]==LOOKUP42,
           "CONTRACT_LOOKUP_PROVENANCE_CHANGED")
    reject(contract["authority"]["parent_pr665"]==HEAD and
           contract["authority"]["pr684_unmerged"]==PR684 and
           contract["authority"]["historical_checkout"]==HISTORY,
           "CONTRACT_SOURCE_PIN_DRIFT")
    parent_json=s["species_only"]
    reject(set(parent_json)=={"species","equations","reactions"} and
           parent_json["equations"]=={} and parent_json["reactions"]==[],
           "PUBLIC_D_CURRENT_CHEMISTRY_NOT_EMPTY")
    reject(set(parent_json["species"])=={"e","O2","O","O2p","Om","Op"},
           "PUBLIC_D_CURRENT_SPECIES_CHANGED")
    for id,charge in {"e":-1,**ION}.items():
        reject(parent_json["species"][id]["charge_number"]==charge,
               "ORIGINAL_CHARGE_CHANGED_"+id)
    option=s["option"]
    reject("fvm_species = 'O2p Om Op'" in option and
           "fem_species = 'e'" in option,
           "PR684_FVM_SELECTION_CHANGED")
    reject("[Chemistry]" not in option,
           "PR684_CURRENT_CHEMISTRY_PRECONDITION_CHANGED")
    c=s["candidate_code"]
    reject("P6_D1_HISTORICAL_ELECTRON_TABLE_SHA_MISMATCH" in c and
           LOOKUP42 in c and
           "len(removed) != 4" in c and
           all(id in c for id in TRANSPORT_MANUAL),
           "PR684_4_MATERIAL_CUTOVER_OR_TABLE_PIN_CHANGED")
    cpp=s["dd_cpp"]
    reject("FV species kernels require [Physics]/[Plasmas]/[Transport]/[Chemistry]" in cpp and
           "requires a nonzero volume reaction source in Chemistry JSON." in cpp and
           "hasSpeciesSource" in cpp and
           "dont_create_kernels" in cpp,
           "CHEMISTRY_PRECONDITION_CXX_CHANGED")
    materials=s["dd_material_cpp"]
    reject("constexpr Real energy_factor = 5.0 / 3.0;" in materials and
           'MooseEnum("reduced physical", "reduced")' in materials and
           "e_energy_eV" in materials,
           "FIVE_THIRDS_ENERGY_OR_REDUCED_UNIT_CONTRACT_CHANGED")
    for case in ("417","941"):
        doc=s["newonly"][case]
        expected_sha,selected=S6JSON[case]
        reject(s["newonly_sha"][case]==expected_sha,
               "NEWONLY_JSON_SHA_CHANGED_"+case)
        reject(len(doc["species"])==7 and
               set(doc["species"])=={"e","O2","O","O2p","Om","Op","O2a"},
               "NEWONLY_SPECIES_COUNT_OR_ID_"+case)
        reject(len(doc["reactions"])==8 and len(doc["equations"])==8,
               "CHEMISTRY_REACTIONS_NOT_EIGHT_"+case)
        ids=[x["id"] for x in doc["reactions"]]
        reject(set(ids)==REQUIRED_REACTIONS|{selected} and len(set(ids))==8 and
               set(doc["equations"])==set(ids),
               "CASE_REACTION_BRANCH_OR_DUPLICATE_"+case)
        for id,charge in {"e":-1,**ION}.items():
            reject(doc["species"][id]["charge_number"]==charge,
                   "S6_CHARGE_CHANGED_"+case+"_"+id)
        reject(doc["species"]["e"]["transport_coef"]=={
            "type":"lookup","file":"../../Issue91_real_qvt_r3/r3_e0/electron_moments.txt",
            "unit":"reduced","bounds_policy":"clamp"},
            "NEWONLY_E_REDUCED_LOOKUP_CHANGED_"+case)
        for id in ION:
            reject(doc["species"][id]["transport_coef"]=={
                "type":"constant","file":"none","unit":"physical",
                "mobility":10,"diffusivity":0.25851999786435537},
                "S6_ION_TRANSPORT_CHANGED_"+case+"_"+id)
            nonzero_any=any(rx.get("products",{}).get(id,0)!=rx.get("reactants",{}).get(id,0)
                            for rx in doc["reactions"])
            reject(nonzero_any,"CHEMISTRY_ION_NO_NONZERO_SOURCE_"+case+"_"+id)
    reject(contract["D4"]["generated_FV_requirements"]["source_functors"]==
           ["S_O2p_molar","S_Om_molar","S_Op_molar"] and
           contract["D4"]["generated_FV_requirements"]["retire_all_legacy_ion_FV"].startswith(
               "14 Native ion FVKernel + 12 Native ion FVBC"),
           "D4_OWNER_SOURCE_OR_26_TO_0_RULE_CHANGED")
    reject(contract["D4"]["material_retire_count"]==4 and
           contract["D4"]["generated_FV_requirements"]["generated_Warehouse_each_case"]==
           {"FV_Kernel":12,"FV_BC":12,"electron_FEM_BC":8},
           "D4_4_OWNER_OR_12_12_8_COUNT_CHANGED")
    reject(contract["newly_frozen_scope"]["D4_REAL_CODE_INTEGRATION"]=="NOT_IMPLEMENTED" and
           contract["newly_frozen_scope"]["PR684_MERGE"]=="KEEP_HOLD" and
           contract["newly_frozen_scope"]["SCIENCE"]=="SCIENCE_HOLD",
           "FALSE_NATIVE_SUCCESS_OR_SCIENCE_PROMOTION")
    return {"100_row":r100,"42_row":r42,"case_reactions":{
        c:sorted(x["id"] for x in s["newonly"][c]["reactions"]) for c in ("417","941")}}

def negative_controls(s):
    checks = [
        ("100_SHA", lambda v: v.__setitem__("lookup100",v["lookup100"]+b"\n#not-original")),
        ("42_SHA",lambda v: v.__setitem__("lookup42",v["lookup42"]+b"\n#not-prepared")),
        ("COMMON_LOOKUP_COLLAPSE",lambda v:v.__setitem__("lookup100",v["lookup42"])),
        ("CONTRACT_LOOKUP_MODE",lambda v:v["contract"]["modes"]["historical_100"].__setitem__("sha256",LOOKUP42)),
        ("E_CHARGE",lambda v:v["species_only"]["species"]["e"].__setitem__("charge_number",1)),
        ("O2P_CHARGE",lambda v:v["newonly"]["417"]["species"]["O2p"].__setitem__("charge_number",-1)),
        ("OM_CHARGE",lambda v:v["newonly"]["417"]["species"]["Om"].__setitem__("charge_number",1)),
        ("OP_CHARGE",lambda v:v["newonly"]["941"]["species"]["Op"].__setitem__("charge_number",-1)),
        ("DROP_417_REACTION",lambda v:v["newonly"]["417"]["reactions"].pop()),
        ("DROP_941_REACTION",lambda v:v["newonly"]["941"]["reactions"].pop()),
        ("SWAP_VARIANT_EI",lambda v:v["newonly"]["417"]["reactions"][-1].__setitem__("id","EI-941")),
        ("MOBILITY_CHANGE",lambda v:v["newonly"]["941"]["species"]["Om"]["transport_coef"].__setitem__("mobility",12)),
        ("MISSING_SOURCE_FUNCTOR",lambda v:v["contract"]["D4"]["generated_FV_requirements"].__setitem__("source_functors",["S_O2p_molar","S_Op_molar"])),
        ("REMOVE_CHEMISTRY_REQUIREMENT",lambda v:v.__setitem__("dd_cpp",v["dd_cpp"].replace("FV species kernels require [Physics]/[Plasmas]/[Transport]/[Chemistry]","allow fallback"))),
        ("RELAX_KERNEL_OWNER",lambda v:v["contract"]["D4"]["generated_FV_requirements"].__setitem__("retire_all_legacy_ion_FV","keep old 26")),
        ("FALSE_NATIVE_PASS",lambda v:v["contract"]["newly_frozen_scope"].__setitem__("D4_REAL_CODE_INTEGRATION","PASS")),
    ]
    caught=[]
    for name,mutation in checks:
        variant=copy.deepcopy(s)
        mutation(variant)
        try:static_contract(variant)
        except AssertionError:caught.append(name)
        else:raise AssertionError("NEGATIVE_MUTANT_WAS_NOT_REJECTED:"+name)
    reject(len(caught)==len(checks),"NEGATIVE_GUARD_COVERAGE_CHANGED")
    return caught

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--parent",type=Path,required=True)
    p.add_argument("--candidate",type=Path,required=True)
    p.add_argument("--history",type=Path,required=True)
    p.add_argument("--contract",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    x=p.parse_args()
    reject(git_head(x.parent)==HEAD,"HEAD_PR665_NOT_EXACT")
    reject(git_head(x.candidate)==PR684,"HEAD_PR684_NOT_EXACT")
    reject(git_head(x.history)==HISTORY,"HEAD_HIST_NOT_EXACT")
    def read(root,path):return (root/path).read_bytes()
    code=read(x.candidate,"experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py").decode()
    stem="experiments/Issue402_plasma_dsl_g1"
    s={
        "contract":json.loads(x.contract.read_bytes()),
        "lookup100":read(x.history,LOOKUP_ORIGINAL_PATH),
        "lookup42":read(x.history,LOOKUP_PREPARED_PATH),
        "species_only":json.loads(read(x.parent,stem+"/plasma_species_only.json")),
        "option":overlay(code),
        "candidate_code":code,
        "dd_cpp":read(x.candidate,"physics_app/src/physics/plasma/DDContinuityEq.C").decode(),
        "dd_material_cpp":read(x.parent,"physics_app/src/materials/DDTransportMaterial.C").decode(),
        "newonly":{case:json.loads(read(x.parent,JSON_DIR+f"/unified_s6_{case}_newonly.json"))
                   for case in ("417","941")},
        "newonly_sha":{case:sha(read(x.parent,JSON_DIR+f"/unified_s6_{case}_newonly.json"))
                   for case in ("417","941")}
    }
    valid=static_contract(s)
    negatives=negative_controls(s)
    receipt={
       "schema":"issue672.p6_d2_d4.immutable_source_contract_guard_receipt.v1",
       "source":{"parent":HEAD,"candidate":PR684,"history":HISTORY},
       "positive":"PASS_ACTUAL_SOURCE_AND_LOOKUP_SHA_CONTRACT_ONLY",
       "negative_mutants":{"passed":len(negatives),"total":len(negatives),"names":negatives},
       "lookups":{"100":dict(sha256=sha(s["lookup100"]),**valid["100_row"]),
                  "42":dict(sha256=sha(s["lookup42"]),**valid["42_row"])},
       "mechanisms":valid["case_reactions"],
       "PR684_actual_D_Chemistry_enabled":False,
       "PR684_actual_D_native_P2":"HOLD_PRE_P05",
       "contract_D2":"PASS_BOUND_DATA_AUTHORITY_SPLIT",
       "contract_D4":"PASS_DESIGN_GATES_ONLY",
       "D4_real_implementation":"NOT_IMPLEMENTED",
       "scientific_equivalence_100_vs_42":"NOT_CLAIMED",
       "native_P3_P4":"NOT_RUN",
       "science":"SCIENCE_HOLD"
    }
    x.output.parent.mkdir(parents=True,exist_ok=True)
    x.output.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print("P6_D2_D4_CONTRACT_GUARD_PASS",len(negatives),len(negatives),
          receipt["lookups"]["100"]["sha256"],receipt["lookups"]["42"]["sha256"])

if __name__=="__main__":
    main()
