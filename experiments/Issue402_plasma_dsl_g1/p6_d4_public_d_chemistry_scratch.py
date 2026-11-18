"""P6-D4 explicit opt-in Public D Chemistry FV source pilot in disposable P2 Scratch.

This is a diagnostic candidate. Never update historical source or PR684/PR665.
It does not certify energy/BC science or P05 warehouse without actual native logs.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import re

PILOT=Path(__file__).resolve().parent
CHEM=PILOT/"chemistry"
RATE_TABLE_SHA="35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b"
ARCHIVED_MECHANISM_BLOB={"417":"87ed65fb1fda5102616c8b1095ca296125ca2a89",
                         "941":"d7fc036054fa1c1eb025d4edae89eeb96a5f526f"}
EXPECTED_COMMON={"EI-02","EI-17","EI-415","EI-401","EI-407","EI-2069","H25"}
CHARGES={"e":-1,"O2p":1,"Om":-1,"Op":1}
EXPECTED_ALIAS={"O2p":("ion_mobility","ion_diffusion"),
                "Om":("negative_ion_mobility","negative_ion_diffusion"),
                "Op":("atomic_positive_ion_mobility","atomic_positive_ion_diffusion")}
PROGRESS_NAMES={"R_elastic_O2":"R_EI02","R_elastic_O":"R_EI17",
                "R_ion_O2":"R_EI415"}
SOURCE_OWNERS=(
    "electron_transport",
    "O2p_species_transport_alias",
    "Om_species_transport_alias",
    "Op_species_transport_alias")

def sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def load_python(filename:Path,module_name:str):
    spec=importlib.util.spec_from_file_location(module_name,filename)
    if spec is None or spec.loader is None:
        raise ValueError("P6_D4_MODULE_UNAVAILABLE:"+filename.name)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def plan(chem:Path,ordered:list[str],case:str)->tuple[dict[Path,bytes],dict]:
    """Plan all exact-source changes in memory, no on-disk edits before gates."""
    if case not in ("417","941") or len(ordered)!=11 or Path(ordered[-1]).name!="migrated_continuity.i":
        raise ValueError("P6_D4_CASE_OR_11_LAYER_MISMATCH")
    names=[Path(p).name for p in ordered]
    if len(set(names))!=11 or any(Path(p).name!=p.split("/")[-1] or not p.endswith(".i")
                                   for p in ordered):
        raise ValueError("P6_D4_UNSAFE_OR_DUPLICATE_LAYER")
    if not chem.is_dir() or any(not(chem/n).is_file() or (chem/n).is_symlink() for n in names):
        raise ValueError("P6_D4_LAYER_NOT_STAGED_OR_SYMLINK")
    pjson=chem/"plasma_species_only.json"
    if not pjson.is_file() or pjson.is_symlink():
        raise ValueError("P6_D4_TRANSPORT_JSON_NOT_STAGED")
    raw={n:(chem/n).read_bytes() for n in names}
    document=json.loads(pjson.read_bytes())
    if set(document)!={"species","reactions","equations"} or document["reactions"] or document["equations"]:
        raise ValueError("P6_D4_PUBLIC_D_SPECIES_ONLY_BASE_NOT_EMPTY")
    if set(document["species"])!={"e","O2","O","O2p","Om","Op"}:
        raise ValueError("P6_D4_PUBLIC_D_SPECIES_IDS_CHANGED")
    for id,charge in CHARGES.items():
        actual=document["species"][id]
        if actual.get("charge_number")!=charge or not isinstance(actual.get("initial_number_density"),(int,float)):
            raise ValueError("P6_D4_DENSITY_OR_CHARGE_CHANGED_"+id)
    table=(chem/"../Issue91_real_qvt_r3/r3_e0/electron_moments.txt").resolve()
    if not table.is_file() or table.is_symlink() or sha(table.read_bytes())!=RATE_TABLE_SHA:
        raise ValueError("P6_D4_PREPARED42_SHA_MISMATCH")
    e=document["species"]["e"]
    for k,v in {"transport_coef":"lookup","table_units":"reduced",
                "pressure":"p","gas_temperature":"T_g_fixed",
                "bounds_policy":"clamp","energy_transport_coef":"fluid",
                "table_file":"../Issue91_real_qvt_r3/r3_e0/electron_moments.txt"}.items():
        if e.get(k)!=v:
            raise ValueError("P6_D4_E_PARTICLE_OR_ENERGY_TRANSPORT_DRIFT_"+k)
    for id,(m,d) in EXPECTED_ALIAS.items():
        ion=document["species"][id]
        if any(ion.get(k)!=v for k,v in {"transport_coef":"functor","mobility":m,"diffusivity":d}.items()):
            raise ValueError("P6_D4_ION_TRANSPORT_SOURCE_DRIFT_"+id)
    original=(CHEM/f"unified_s6_{case}.json")
    rawmechanism=original.read_bytes()
    mech=json.loads(rawmechanism)
    if set(mech["species"])!={"e","O2","O","O2p","Om","Op","O2a"}:
        raise ValueError("P6_D4_MECHANISM_SPECIES_CHANGED")
    reactions=mech["reactions"]
    reaction_ids=[item["id"] for item in reactions]
    if (len(reactions)!=8 or len(set(reaction_ids))!=8 or
        set(reaction_ids)!=EXPECTED_COMMON|{f"EI-{case}"} or
        set(mech["equations"])!=set(reaction_ids)):
        raise ValueError("P6_D4_MECHANISM_REACTION_BRANCH_CHANGED")
    for id in CHARGES:
        if mech["species"][id]["charge_number"]!=document["species"][id]["charge_number"]:
            raise ValueError("P6_D4_MECHANISM_CHARGE_CHANGED_"+id)
    for id in EXPECTED_ALIAS:
        if not any(x["products"].get(id,0)!=x["reactants"].get(id,0)
                   for x in reactions):
            raise ValueError("P6_D4_ION_SOURCE_ABSENT_"+id)
    # Preserve original Public D transport and IC ownership; add only the
    # established neutral O2a and exactly the validated 8 true reactions.
    doc=dict(document)
    doc["species"]=dict(document["species"])
    doc["species"]["O2a"]=mech["species"]["O2a"]
    doc["equations"]=mech["equations"]
    doc["reactions"]=mech["reactions"]
    ovl=raw["migrated_continuity.i"].decode("utf-8")
    if (ovl.count("    files = plasma_species_only.json")==0 or
        ovl.count("      [DriftDiffusion]")!=1 or "[Chemistry]" in ovl):
        raise ValueError("P6_D4_D_OPTION_SOURCE_OVERLAY_NOT_EXACT")
    if ovl.count("    files = plasma_species_only.json")!=1:
        raise ValueError("P6_D4_MULTIPLE_PHYSICS_FILE_OWNERS")
    after_overlay=ovl.replace(
        "    files = plasma_species_only.json",
        f"    files = public_D_{case}_chemistry.json",1).replace(
        "      [DriftDiffusion]",
        "      [Chemistry]\n        block = plasma\n      []\n      [DriftDiffusion]",1)
    if after_overlay.count("[Chemistry]")!=1:
        raise ValueError("P6_D4_CHEMISTRY_NOT_ENABLED_EXACTLY_ONCE")
    # Retire the exactly 26 known old Ion FV owners before generating 12+12.
    donor=load_python(CHEM/"retire_s6_ion_fv_owners.py",
                      "p6_d4_original_canonical_26_retirement")
    before_text={name:b.decode("utf-8") for name,b in raw.items()}
    after,receipt=donor.cutover_texts(before_text)
    if len(receipt["retired_owners"])!=26 or receipt["old_native_fv_kernels"]!=14 or receipt["old_native_fv_bcs"]!=12:
        raise ValueError("P6_D4_ION26_RETIRE_COUNT_NOT_EXACT")
    # Chemistry generates ONE FE electron particle Source functor for all
    # real EI reactions; retain historical electron-energy RHS Kernels, but
    # retire precisely three *particle* FunctorKernel owners before P05.
    # This is not wholesale removal of the nine electron/energy Kernels.
    sources=load_python(CHEM/"prepare_s6_run_input.py",
                        "p6_d4_historical_electron_particle_source_owners")
    old_electron_particle=[]
    for layer,owner_map in {**sources.BASE_REMOVE,**sources.VARIANT_REMOVE[case]}.items():
        if layer not in after:
            raise ValueError("P6_D4_ELECTRON_SOURCE_LAYER_ABSENT_"+layer)
        for name,(variable,functor) in owner_map.items():
            if variable!="log_e":
                continue
            if name=="electron_time" or functor in ("0",""):
                raise ValueError("P6_D4_ELECTRON_PARTICLE_OWNER_UNEXPECTED")
            old=after[layer]
            after[layer]=sources.remove_one(old,name,variable,functor)
            old_electron_particle.append({
                "layer":layer,"owner":name,"variable":variable,"source_functor":functor,
                "before_file_sha256":sha(old.encode()),"after_file_sha256":sha(after[layer].encode())})
    if len(old_electron_particle)!=3:
        raise ValueError("P6_D4_ELECTRON_PARTICLE_3_TO_ONE_NOT_EXACT")
    # Native source functors R_elastic_O2/O and R_ion_O2 are historical
    # producers; retain their actual numerical producer/consumer objects,
    # only canonicalize the identifier tokens as original Chemistry staging does.
    replaced={}
    for old,new in PROGRESS_NAMES.items():
        matches=sum(len(re.findall(r"(?<![A-Za-z0-9_])"+re.escape(old)+r"(?![A-Za-z0-9_])",val))
                    for val in after.values())
        if matches==0:
            raise ValueError("P6_D4_EXPECTED_HISTORICAL_RATE_PROVIDER_MISSING_"+old)
        replaced[old]={"to":new,"occurrences":matches}
    for name,src in list(after.items()):
        for old,new in PROGRESS_NAMES.items():
            src=re.sub(r"(?<![A-Za-z0-9_])"+re.escape(old)+r"(?![A-Za-z0-9_])",new,src)
        after[name]=src
    after["migrated_continuity.i"]=after_overlay
    changes={chem/name:src.encode("utf-8") for name,src in after.items()
             if src.encode("utf-8")!=raw[name]}
    out=chem/f"public_D_{case}_chemistry.json"
    if out.exists() or out.is_symlink():
        raise ValueError("P6_D4_DIFFERENT_EXISTING_SOURCE_JSON")
    changes[out]=(json.dumps(doc,indent=2,sort_keys=True)+"\n").encode("utf-8")
    return changes,{
        "schema":"issue672.p6_d4.disposable_real_chemistry_source_handoff.pilot.v1",
        "mode":"EXISTING_PUBLIC_RESEARCH_PREPARED_42ROW",
        "case":case,
        "electron_42_row_sha256":RATE_TABLE_SHA,
        "real_mechanism_source":str(original.relative_to(PILOT)),
        "real_mechanism_sha256":sha(rawmechanism),
        "species_count":len(doc["species"]),"reaction_count":len(reactions),
        "mechanism_branch":f"EI-{case}",
        "material_transport_owner_cutover":"PR684_DRIVER_EARLIER_4_PASS_REQUIRED",
        "old_native_ion_owners_retired":26,
        "old_native_ion_kernels_retired":14,
        "old_native_ion_bcs_retired":12,
        "retired_exact_electron_particle_rhs_kernels":old_electron_particle,
        "retired_electron_particle_rhs_count":len(old_electron_particle),
        "legacy_electron_energy_rhs":"PRESERVED_EXACT_NATIVE_UNTIL_NUMERICAL_CONSUMER_REVIEW",
        "generated_electron_particle_rhs":"CHEMISTRY_SIGNED_REAL_7SPECIES_8REACTIONS",
        "retired_ion_details":receipt["retired_owners"],
        "rate_symbol_renames":replaced,
        "file_sha256":{
            str(p.relative_to(chem)):{"before":sha(p.read_bytes()) if p.is_file() else None,"after":sha(data)}
            for p,data in changes.items()
        },
        "native_p2":"NOT_RUN","P05":"NOT_RUN",
        "generated_walls_12plus12":"NOT_OBSERVED",
        "electron_8_BC":"PRESERVED_SOURCE_ONLY_NOT_WAREHOUSE",
        "P3":"NOT_RUN","P4":"NOT_RUN","science":"SCIENCE_HOLD"
    }

def apply(chem:Path,ordered:list[str],case:str)->dict:
    changes,receipt=plan(chem,ordered,case)
    # The only mutations are validated disposable scratch writes.
    for p,b in changes.items():
        p.write_bytes(b)
        if sha(p.read_bytes())!=sha(b):
            raise RuntimeError("P6_D4_SCRATCH_READBACK_FAILURE:"+p.name)
    return receipt
