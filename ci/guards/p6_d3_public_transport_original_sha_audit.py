#!/usr/bin/env python3
"""P6-D3: exact-head, source-only Public D original Transport/Lookup/charge SHA audit.

No private EI data, Native compilation, solver or historical input mutation.
"""
from __future__ import annotations
import argparse
import ast
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from zipfile import ZipFile

HEAD = "74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f"
P3_X_ZIP_SHA = "592a7c82834bab841f6a2e1807db305d0eff1e953f50a0dcc6d7e21ff8820111"
ELECTRON_42_SHA = "35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
FILES = {
    "public_species": ("experiments/Issue402_plasma_dsl_g1/plasma_species_only.json",
                       "c563f54b4914773f153b170fb8b5b63f2687c170"),
    "public_base": ("experiments/Issue402_plasma_dsl_g1/native/s6_c0_physics_base_no_d1.i",
                    "793f3f24bc95bf71d0b2537288cb2ecc8a5f74fa"),
    "public_runner": ("experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py",
                      "a6414baf70590b79f4b4ee4cb16c4b9039355f40"),
    "original_lookup": ("experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt",
                        "bedcaf17fb3ef93ba8973cc6b32aa6e783e2292a"),
    "material_cpp": ("physics_app/src/materials/DDTransportMaterial.C",
                     "e75687d73d8ca6fead0eff411ad7ffbb814a6909"),
    "newonly417": ("experiments/Issue402_plasma_dsl_g1/chemistry/unified_s6_417_newonly.json",
                   "4a05649b42b798f566d5e455ef46be347ea2a461"),
    "newonly941": ("experiments/Issue402_plasma_dsl_g1/chemistry/unified_s6_941_newonly.json",
                   "9568e2cae6640a755f9403c4f58e077c801b998c")
}
IONS = {
    "O2p": {"charge": 1, "mobility": "ion_mobility", "diffusion": "ion_diffusion",
            "wall": "ion_wall_flux", "mass": 0.032},
    "Om": {"charge": -1, "mobility": "negative_ion_mobility",
           "diffusion": "negative_ion_diffusion", "wall": "negative_ion_wall_flux",
           "mass": 0.016},
    "Op": {"charge": 1, "mobility": "atomic_positive_ion_mobility",
           "diffusion": "atomic_positive_ion_diffusion", "wall": "atomic_positive_ion_wall_flux",
           "mass": 0.016},
}
EXPECTED_KEYS = ["p_fixed", "T_g_fixed", "ion_mobility", "ion_diffusion",
                 "negative_ion_mobility", "negative_ion_diffusion",
                 "atomic_positive_ion_mobility", "atomic_positive_ion_diffusion", "carrier_one"]
EXPECTED_VALUES = ["1.333223684", "300", "10", "0.25851999786435537",
                   "10", "0.25851999786435537", "10", "0.25851999786435537", "1.0"]

def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()

def block(text: str, name: str) -> str:
    pat = re.compile(r"(?ms)^  \[" + re.escape(name) + r"\]\n(?P<body>.*?)^  \[\][ \t]*$")
    matches = list(pat.finditer(text))
    if len(matches) != 1:
        raise AssertionError(f"BLOCK_NOT_SINGLE:{name}:{len(matches)}")
    return matches[0].group("body")

def param(body: str, key: str) -> str:
    found = re.findall(r"(?m)^    " + re.escape(key) + r"\s*=\s*(.*?)\s*$", body)
    if len(found) != 1:
        raise AssertionError("PARAM_NOT_SINGLE:" + key)
    return found[0]

def rows(data: bytes, expected: int) -> dict:
    decoded = data.decode("utf-8")
    lines = [x for x in decoded.splitlines() if x.strip()]
    if len(lines) != expected:
        raise AssertionError(f"LOOKUP_ROWS:{len(lines)}!={expected}")
    parsed = []
    for ln in lines:
        columns = ln.split()
        if len(columns) != 3:
            raise AssertionError("LOOKUP_COLUMNS_NOT_THREE")
        values = tuple(float(k) for k in columns)
        if not all(math.isfinite(x) for x in values) or any(v <= 0 for v in values):
            raise AssertionError("LOOKUP_NONPOSITIVE_OR_NONFINITE")
        parsed.append(values)
    if not all(a[0] < b[0] for a,b in zip(parsed, parsed[1:])):
        raise AssertionError("LOOKUP_AXIS_NOT_STRICTLY_INCREASING")
    return {"rows":len(lines), "columns":3, "first":lines[0], "last":lines[-1],
            "eV_range":[parsed[0][0],parsed[-1][0]],"raw_sha256":sha(data)}

def check_species(document: dict) -> None:
    d = document["species"]
    if set(d) != {"e","O2","O","O2p","Om","Op"}:
        raise AssertionError("SPECIES_SET_CHANGED")
    for species, expected in [("e",-1),("O2p",1),("Om",-1),("Op",1)]:
        rec = d[species]
        if rec["charge_number"] != expected or set(rec) != {"charge_number","elements"}:
            raise AssertionError("PUBLIC_D_CHARGE_OR_SCHEMA_CHANGED:"+species)
        if "transport_coef" in rec:
            raise AssertionError("PUBLIC_D_SPECIES_TRANSPORT_UNEXPECTED:"+species)
    if document["equations"] != {} or document["reactions"] != []:
        raise AssertionError("PUBLIC_D_NONEMPTY_CHEMISTRY")

def check_overlay(overlay: str) -> None:
    if sha(overlay.encode()) != "edf3f8e8194927e93783d136066799d60df2673af9245d6d4b990fb7d267b513":
        raise AssertionError("PUBLIC_D_OVERLAY_PIN_CHANGED")
    for id, spec in IONS.items():
        bb = block(overlay, id + "_species_transport_alias")
        if (param(bb,"type") != "DDTransportMaterial" or
            param(bb,"model") != "functor" or
            param(bb,"species_id") != id or
            param(bb,"mobility_source") != spec["mobility"] or
            param(bb,"diffusivity_source") != spec["diffusion"]):
            raise AssertionError("PUBLIC_D_ALIAS_BINDING_CHANGED:"+id)

def audit(repo: Path, archive: Path) -> dict:
    if git("rev-parse","HEAD") != HEAD:
        raise AssertionError("SOURCE_HEAD_CHANGED")
    origin = {}
    for key,(file,pin) in FILES.items():
        actual_git_sha = git("rev-parse", f"HEAD:{file}")
        if actual_git_sha != pin:
            raise AssertionError("GIT_BLOB_PIN_MISMATCH:" + key)
        data = (repo / file).read_bytes()
        if sha(data) != sha(subprocess.check_output(["git","show",f"HEAD:{file}"])):
            raise AssertionError("LOCAL_SOURCE_DIFFERS_FROM_GIT:" + key)
        origin[key] = {"git_blob":actual_git_sha,"sha256":sha(data),"bytes":len(data),"path":file}
    species_document=json.loads((repo / FILES["public_species"][0]).read_bytes())
    check_species(species_document)
    raw_base = (repo / FILES["public_base"][0]).read_text()
    constants = block(raw_base,"constants")
    if param(constants,"type") != "ADGenericFunctorMaterial":
        raise AssertionError("PUBLIC_D_CONSTANTS_FACTORY_CHANGED")
    names=param(constants,"prop_names").strip("'").split()
    vals=param(constants,"prop_values").strip("'").split()
    if names != EXPECTED_KEYS or vals != EXPECTED_VALUES:
        raise AssertionError("PUBLIC_D_MANUAL_CONSTANTS_VALUES_CHANGED")
    values=dict(zip(names,vals))
    for id, spec in IONS.items():
        bb=block(raw_base, spec["wall"])
        if (param(bb,"mobility")!=spec["mobility"] or
            float(param(bb,"charge_number"))!=spec["charge"] or
            float(param(bb,"molar_mass"))!=spec["mass"]):
            raise AssertionError("WALL_CHARGE_MOBILITY_MASS_CHANGED:"+id)
        if values[spec["mobility"]]!="10" or values[spec["diffusion"]]!="0.25851999786435537":
            raise AssertionError("ION_MANUAL_COEFFICIENT_CHANGED:"+id)
    charge_body=block(raw_base,"charge_number_density")
    if param(charge_body,"expression").strip("'")!="ni+nop-ne-nm":
        raise AssertionError("POISSON_CHARGE_SIGN_CHANGED")
    source_runner=(repo / FILES["public_runner"][0]).read_text()
    assignments=ast.parse(source_runner)
    overlay=None
    for node in assignments.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="OVERLAY" for t in node.targets):
            overlay=ast.literal_eval(node.value)
    if overlay is None:
        raise AssertionError("PUBLIC_D_OVERLAY_MISSING")
    check_overlay(overlay)
    original_e=block(raw_base,"electron_transport")
    expected_e={"type":"PhysicsElectronTransportLookupMaterial",
                "property_table_file":"'../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'",
                "mean_energy":"mean_en_solved","pressure":"p",
                "gas_temperature":"T_g_fixed","bounds_policy":"clamp","block":"plasma"}
    for name,value in expected_e.items():
        if param(original_e,name)!=value:
            raise AssertionError("ORIGINAL_E_LOOKUP_INPUT_CHANGED:"+name)
    if set(re.findall(r"(?m)^    ([A-Za-z_]\w*)\s*=",original_e))!=set(expected_e):
        raise AssertionError("ORIGINAL_E_LOOKUP_EXTRA_PARAMETER")
    cpp=(repo / FILES["material_cpp"][0]).read_text()
    for required in ['"Constant species mobility [m^2/(V s)]."',
                     '"Constant species diffusivity [m^2/s]."',
                     '"Three-column lookup table: e_energy_eV [eV], mobility, diffusivity. "',
                     'MooseEnum("reduced physical", "reduced")',
                     'constexpr Real energy_factor = 5.0 / 3.0;',
                     'getFunctorByName<ADReal>("e_energy_eV")']:
        if required not in cpp:
            raise AssertionError("CXX_UNIT_ENERGY_CONTRACT_CHANGED:"+required)
    e100=rows((repo / FILES["original_lookup"][0]).read_bytes(),100)
    data=archive.read_bytes()
    if sha(data)!=P3_X_ZIP_SHA:
        raise AssertionError("P3X_ARCHIVE_PIN_CHANGED")
    with ZipFile(archive) as zipped:
        if zipped.testzip() is not None:
            raise AssertionError("P3X_ARCHIVE_CRC_FAILURE")
        stage={}
        for case in ("417","941"):
            p=f"cases/{case}/experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
            values=zipped.read(p)
            if sha(values)!=ELECTRON_42_SHA:
                raise AssertionError("P3X_TABLE_SHA_CHANGED:"+case)
            stage[case]=rows(values,42)
        if stage["417"]["raw_sha256"]!=stage["941"]["raw_sha256"]:
            raise AssertionError("P3X_CASE_LOOKUP_NOT_IDENTICAL")
    if e100["raw_sha256"]==ELECTRON_42_SHA:
        raise AssertionError("PUBLIC_D_SOURCE_TABLE_WAS_CONFUSED_WITH_NEWONLY_TABLE")
    newonly={}
    for case in ("417","941"):
        j=json.loads((repo/FILES["newonly"+case][0]).read_bytes())
        sj=j["species"]
        if sj["e"]["charge_number"]!=-1 or sj["e"]["transport_coef"]!={
           "type":"lookup","file":"../../Issue91_real_qvt_r3/r3_e0/electron_moments.txt",
           "unit":"reduced","bounds_policy":"clamp"}:
            raise AssertionError("NEWONLY_E_REFERENCE_CHANGED")
        for id,opts in IONS.items():
            if (sj[id]["charge_number"]!=opts["charge"] or
                sj[id]["transport_coef"]!={"type":"constant","file":"none","unit":"physical",
                                             "mobility":10,"diffusivity":0.25851999786435537}):
                raise AssertionError("NEWONLY_ION_UNITS_CHARGE_CHANGED:"+id)
        newonly[case]={"json_sha256":origin["newonly"+case]["sha256"],
                       "e":"lookup/reduced/clamp","ions":"constant/physical",
                       "e_charge":-1,"ion_charge":{k:v["charge"] for k,v in IONS.items()}}
    negatives=0
    for name,wrong in [("e",1),("O2p",-1),("Om",1),("Op",-1)]:
        candidate=copy.deepcopy(species_document)
        candidate["species"][name]["charge_number"]=wrong
        try:check_species(candidate)
        except AssertionError:negatives+=1
        else:raise AssertionError("NEGATIVE_MUTANT_NOT_REJECTED:charge_"+name)
    candidate=copy.deepcopy(species_document)
    candidate["species"]["e"]["transport_coef"]={"type":"constant"}
    try:check_species(candidate)
    except AssertionError:negatives+=1
    else:raise AssertionError("NEGATIVE_MUTANT_NOT_REJECTED:json_transport")
    for before,after in [("mobility_source = ion_mobility","mobility_source = Om_mobility"),
                         ("diffusivity_source = negative_ion_diffusion","diffusivity_source = ion_diffusion"),
                         ("species_id = Op","species_id = Om")]:
        candidate=overlay.replace(before,after,1)
        if candidate==overlay:
            raise AssertionError("MUTATION_TARGET_NOT_FOUND:"+before)
        try:check_overlay(candidate)
        except AssertionError:negatives+=1
        else:raise AssertionError("NEGATIVE_MUTANT_NOT_REJECTED:overlay_"+before)
    report={
        "schema":"issue672.p6_d3.public_d_transport_lookup_original_sha.v1",
        "source_head":HEAD,"source":origin,
        "public_D_status":"SOURCE_ORIGIN_PROVEN__RUNTIME_TRANSPORT_MISSING_JSON_HOLD",
        "public_D_raw_json":{"transport_coef_present_for_any_of_four":False,
             "charge":{"e":-1,"O2p":1,"Om":-1,"Op":1}},
        "manual_ion_producers":{
            k:{"coefficient_owner":"[FunctorMaterials]/constants",
               "original_mobility_functor":v["mobility"],
               "original_diffusivity_functor":v["diffusion"],
               "mobility":10,"diffusivity":0.25851999786435537,
               "mobility_unit":"m^2/(V s)","diffusivity_unit":"m^2/s",
               "charge_number":v["charge"],"molar_mass":v["mass"]}
            for k,v in IONS.items()},
        "original_electron_lookup":{"owner":"[FunctorMaterials]/electron_transport",
             "factory":"PhysicsElectronTransportLookupMaterial",
             "original_block_sha256":sha(("  [electron_transport]\n"+original_e+"  []").encode()),
             "table_path":expected_e["property_table_file"],
             "coordinate_legacy":"mean_en_solved",
             "gas_pressure_functor":"p","gas_temperature_functor":"T_g_fixed",
             "table_units":"reduced","bounds_policy":"clamp",
             "file_origin":"repository original 100-row table","table":e100},
        "public_D_overlay":{"sha256":sha(overlay.encode()),"physics_json":"plasma_species_only.json",
            "ion_dd_materials":3,"model":"functor",
            "electron_json_transport":"MISSING",
            "ion_manual_alias_map":{k:{"mobility_source":v["mobility"],"diffusivity_source":v["diffusion"]} for k,v in IONS.items()}},
        "newonly_distinct_stage":{"archive_sha256":sha(data),
            "stage_electron_lookup_42_row":stage,"json_source":newonly,
            "not_equal_to_public_D_100_row_table":True},
        "cxx_units":{"electron_reduced":"mobility*Nn, diffusivity*Nn, Nn=p/(k_B*T)",
            "axis":"e_energy_eV [eV]","physical_mobility":"m^2/(V s)",
            "physical_diffusivity":"m^2/s","energy_projection_factor":"5/3"},
        "negatives_rejected":negatives,
        "gates":{"ORIGINAL_PUBLIC_D_RAW_SOURCE_SHA":"PASS",
                 "ORIGINAL_E_LOOKUP_100_ROWS_SHA":"PASS",
                 "ION_MANUAL_PRODUCER_CHARGE_UNIT":"PASS_3_OF_3",
                 "PUBLIC_D_E_JSON_TRANSPORT":"HOLD_MISSING",
                 "NEWONLY_42_ROW_LOOKUP_DISTINCT":"PASS",
                 "NATIVE_PUBLIC_D":"NOT_RUN",
                 "SCIENCE":"SCIENCE_HOLD"},
        "private_raw_rates_included":False
    }
    return report

def main() -> None:
    a=argparse.ArgumentParser()
    a.add_argument("--repo",type=Path,required=True)
    a.add_argument("--p3x-zip",type=Path,required=True)
    a.add_argument("--out",type=Path,required=True)
    opts=a.parse_args()
    doc=audit(opts.repo,opts.p3x_zip)
    opts.out.parent.mkdir(parents=True,exist_ok=True)
    opts.out.write_text(json.dumps(doc,indent=2,sort_keys=True)+"\n")
    print("P6_D3_SOURCE_ORIGIN_PASS",doc["source_head"],
          "PUBLIC_E_TABLE_SHA",doc["original_electron_lookup"]["table"]["raw_sha256"],
          "P3X_E_TABLE_SHA",doc["newonly_distinct_stage"]["stage_electron_lookup_42_row"]["417"]["raw_sha256"],
          "MUTANTS_REJECTED",doc["negatives_rejected"],
          "PUBLIC_D_TRANSPORT_HOLD")
if __name__=="__main__":
    main()
