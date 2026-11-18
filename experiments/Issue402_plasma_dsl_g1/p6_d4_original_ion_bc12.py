"""P6-D4 original-law ion FV BC-only handoff: 12 exact archived operators.

No new wall, current, sheath or electron flux Materials are allowed. A separate
PlasmasAction original_wall_flux mode generates only the exact corresponding BC
residuals from one original SHA-gated ion flux owner per species.

This is a source input and BC residual semantics contract, not P3/P4 approval.
"""
from __future__ import annotations
import hashlib
import importlib.util
from pathlib import Path

GENERAL="inlet outlet plasma_electrode plasma_metal plasma_right"
DIELECTRIC={
    "cover":"plasma_cover", "wafer":"plasma_wafer",
    "focus_ring":"plasma_focus_ring",
}
SPECIES={
    "O2p":("ion","ion_wall_flux","n_i_physical",1,"0.032","O2p_mobility"),
    "Om":("negative_ion","negative_ion_wall_flux","n_m_physical",-1,"0.016","Om_mobility"),
    "Op":("atomic_positive_ion","atomic_positive_ion_wall_flux","n_op_physical",1,"0.016","Op_mobility"),
}
ARCHIVE_BC_SHA={
    "ion_wall":"fa4ad1a51cbcd4b6ffa1dc8fba3438b66b27642a598bc35abca2513b9f0bacb3",
    "negative_ion_wall":"cf5d56c3af0f77832f08139360753ac8c300e24cd86f6fd24158e77893fe375b",
    "atomic_positive_ion_wall":"8a32490bce4f29361270661c094f8d0e45cb3555b8d9ce9127dd725ac340d67f",
    "ion_cover_dielectric":"6cf04ff67cabc68ad5852678c5c83c646495f994c5bf6c7dfc3628d637812d5b",
    "negative_ion_cover_dielectric":"61acf3daa0654c6beb7220c7aaca1f3dbab944e9586a09e756aa2d419014ff02",
    "atomic_positive_ion_cover_dielectric":"f44eddb6f571b5bc1b33cbe08a772bba4dcc86f129f53fe4127b715f47cfbe45",
    "ion_wafer_dielectric":"07256ce1face22d3fbe6b318d5e1857bf61289b2619adfea3cefec707a37b31c",
    "negative_ion_wafer_dielectric":"ce57b0e42089b7266f623359eeb56cc4349cda356b9503ef37fb244e8cedbea3",
    "atomic_positive_ion_wafer_dielectric":"4f6259aa4c0c1d69495581e27e229fc9b4d3e4fb3dcbd59ff09c8ff53ad2937b",
    "ion_focus_ring_dielectric":"830e2cddd31b70308732cf4dab3e7d4327d38c34d0200ec50da4fcf011eee761",
    "negative_ion_focus_ring_dielectric":"b96509870ac57132a0d71588709753b065ec699afe36917cf715480e5480febe",
    "atomic_positive_ion_focus_ring_dielectric":"bd7e0cf631d41a4670e1a744af6c94bc66d57e1aace960acb183249906425e62",
}
ARCHIVE_CURRENT_SHA={
    "cover_surface_current":"acaa407f7dafae72a7b83f0eaefbdcbd29a292e1cb0a8275293acdb2c4bdba0f",
    "wafer_surface_current":"e523769c7b4782a7be3e5b1f926b5cdc5ec31240cc4c1df45760efca9b06b0d2",
    "focus_ring_surface_current":"b7f8870d2c6b4431fc0dff3fa90e158b64edfa5e7f0f1f68371ffc570fe442a2",
}
AVOGADRO="-1.6605390671738466e-24"
ORIGINAL_C0=(
    "rf_elastic_diss_ion_ei20_ei01_400w_adjacent_sheath_wall_closed_"
    "100us_dt1000ns__C0_chemistry_off.i"
)
def sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def fail(msg):
    raise ValueError("P6_D4_BC12_"+msg)

def extract_objects(text:str):
    donor_path=Path(__file__).resolve().parent/"chemistry/retire_s6_ion_fv_owners.py"
    spec=importlib.util.spec_from_file_location("p6_d4_ion26_bc_ledger",donor_path)
    donor=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(donor)
    roots=list(donor.ROOT.finditer(text))
    objs={}
    for obj in donor.BLOCK.finditer(text):
        section=next((root.group(1) for root in reversed(roots)
                      if root.start()<obj.start()),"")
        if section not in ("FVBCs","FunctorMaterials"):
            continue
        key=(section,obj["name"])
        if key in objs:fail("DUPLICATE_SOURCE_OBJECT_"+obj["name"])
        objs[key]={"sha":sha(obj.group(0).encode("utf-8")),
                   "params":donor.parsed_parameters(obj["body"])}
    return objs

def audit_raw_wall_sources(raw_layers:dict[str,bytes])->tuple[dict,dict]:
    if ORIGINAL_C0 not in raw_layers:
        fail("ORIGINAL_C0_MISSING")
    objs=extract_objects(raw_layers[ORIGINAL_C0].decode("utf-8"))
    original={}
    boundary_groups={}
    for id,(prefix,owner,density,charge,mass,mobility) in SPECIES.items():
        # Require preexisting *staged* original wall law, not C2 replacement.
        record=objs.get(("FunctorMaterials",owner))
        if record is None:fail("WALL_FLUX_MATERIAL_MISSING_"+id)
        p=record["params"]
        required={"type":"IonWallFluxMaterial","species_id":id,
                  "ion_number_density":density,"potential":"potential",
                  "mobility":mobility,"gas_temperature":"temperature",
                  "charge_number":str(charge),"molar_mass":mass,
                  "sticking":"1.0","ion_temperature_eV":"0.0",
                  "migration_gate_smoothing_width":"1.0e-3",
                  "use_element_gradient_for_potential":"true","block":"plasma"}
        if p!=required:fail("WALL_LAW_CHANGED_"+id)
        original[owner]={"sha256":record["sha"],"law":p}
        items=[(f"{prefix}_wall",GENERAL,"FVFunctorNeumannBC")]
        items += [(f"{prefix}_{short}_dielectric",sides,
                   "PhysicsFVLogMolarDielectricFluxBC") for short,sides in DIELECTRIC.items()]
        for name,sides,kind in items:
            bc=objs.get(("FVBCs",name))
            if bc is None or bc["sha"]!=ARCHIVE_BC_SHA[name]:
                fail("ORIGINAL_BC_RAW_BLOCK_SHA_CHANGED_"+name)
            required={"type":kind,"variable":"log_"+id,"boundary":sides}
            flux=id+"_wall_number_flux"
            if kind=="FVFunctorNeumannBC":
                required.update(functor=flux,factor=AVOGADRO)
                out_type="FVFunctorNeumannBC"
                out_name=id+"_wall"
            else:
                required.update(signed_number_flux=flux)
                out_type="FVLogMolarDielectricFluxBC"
                short=next(k for k,v in DIELECTRIC.items() if v==sides)
                out_name=id+"_"+short+"_dielectric"
            if bc["params"]!=required:fail("ORIGINAL_BC_SEMANTICS_CHANGED_"+name)
            boundary_groups.setdefault(sides,{})[out_name]={"type":out_type}
            original[name]={"sha256":bc["sha"],"source_params":required,
                            "generated_name":out_name,"generated_type":out_type,
                            "one_to_one_signed_flux":flux,
                            "factor":AVOGADRO if out_type=="FVFunctorNeumannBC" else "1/N_A"}
    for name,expected_sha in ARCHIVE_CURRENT_SHA.items():
        record=objs.get(("FunctorMaterials",name))
        if record is None or record["sha"]!=expected_sha:
            fail("SURFACE_CURRENT_SOURCE_SHA_CHANGED_"+name)
        expr=record["params"]
        if expr != {
            "type":"ADParsedFunctorMaterial",
            "property_name":name.replace("_surface_current","_net_surface_current_density"),
            "functor_names":"O2p_wall_number_flux Op_wall_number_flux Om_wall_number_flux e_wall_number_flux",
            "functor_symbols":"gi gop gm ge",
            "expression":"1.602176634e-19*(gi+gop-gm-ge)",
            "block":"plasma",
        }:
            fail("SURFACE_CURRENT_CHARGE_SIGN_CHANGED_"+name)
        original[name]={"sha256":expected_sha,"law":expr}
    if len(ARCHIVE_BC_SHA)!=12 or len(original)!=18:
        fail("SOURCE_OWNER_CENSUS_NOT_12_PLUS_3_PLUS_3")
    # Two disjoint normal sidesets combine to a single FV BC per ion.
    if set(boundary_groups)!={GENERAL,*DIELECTRIC.values()}:
        fail("BOUNDARY_SIDESET_GROUPS_CHANGED")
    if any(len(bcs)!=3 for bcs in boundary_groups.values()):
        fail("BC_GROUP_SPECIES_COUNT_CHANGED")
    # Existing C++ parser supports these grouped strings; no e BC here, since
    # all 8 historical electron FEM sheath owners remain active in input.
    groups={
        "inlet outlet":{"%s_wall"%id:{"type":"FVFunctorNeumannBC"} for id in SPECIES},
        "plasma_electrode plasma_metal plasma_right":{
            "%s_wall"%id:{"type":"FVFunctorNeumannBC"} for id in SPECIES},
    }
    for short,sides in DIELECTRIC.items():
        groups[sides]={
            "%s_%s_dielectric"%(id,short):{"type":"FVLogMolarDielectricFluxBC"}
            for id in SPECIES}
    return groups,original
