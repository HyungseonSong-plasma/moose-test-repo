#!/usr/bin/env python3
"""P1 ion FV input-only owner preflight (no MOOSE build, no simulation).

Read S6 staged 11 .i layers and unified JSON. The explicitly selected
Continuity fem_species/fvm_species decide FE/FV generation; no owner-mode flag.
Use distinct NEW-ONLY and archived LEGACY-HYBRID validation contracts.
Neither contract activates a Physics ownership mode: fvm_species selects FV.
A clean P0 input is NOT proof that Physics generated FV kernels at runtime.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import zipfile
from pathlib import Path

BLOCK_RE = re.compile(r"^\s*\[([^\]]*)\]\s*$")
ASSIGN_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")

UNRESOLVED_INCLUDE_RE = re.compile(r"(?m)^\s*!include\b")
LEGACY_S6_VARIABLES = {"O2p": "log_ni", "Om": "log_nm", "Op": "log_nop"}
LEGACY_S6_KERNEL_COUNTS = {"O2p": 5, "Om": 4, "Op": 5}
LEGACY_S6_BC_COUNTS = {"O2p": 4, "Om": 4, "Op": 4}
CONTRACTS = ("new-only", "legacy-hybrid")

def scan_layer(text: str):
    stack = []
    found = []
    lines = text.splitlines()
    for n, line in enumerate(lines, 1):
        match = BLOCK_RE.fullmatch(line)
        if match:
            if match[1]:
                stack.append({"name": match[1], "line": n, "params": {}})
            elif stack:
                blk = stack.pop()
                if stack:
                    # Keep a copy of the fully qualified hierarchy from which the
                    # object was closed, rather than guessing based on its name.
                    blk["parent"] = "/".join(x["name"] for x in stack)
                else:
                    blk["parent"] = ""
                found.append(blk)
            continue
        assign = ASSIGN_RE.fullmatch(line)
        if assign and stack:
            stack[-1]["params"][assign[1]] = assign[2].strip("'\"")
    if stack:
        raise ValueError("P1_UNBALANCED_I_BLOCKS")
    return found


def inspect(layers: dict[str, str], mechanism: dict, contract: str = "new-only") -> dict:
    if contract not in CONTRACTS:
        raise ValueError("P1_INVALID_INPUT_CONTRACT")
    errors = []
    blocks = []
    for name, text in layers.items():
        if UNRESOLVED_INCLUDE_RE.search(text):
            errors.append("P1_UNRESOLVED_INCLUDE:" + name)
        for block in scan_layer(text):
            blocks.append({**block, "file": name})
    cs = [b for b in blocks if b["name"] == "Continuity" and
          b["parent"].endswith("/DriftDiffusion")]
    if len(cs) != 1:
        errors.append(f"P1_CONTINUITY_COUNT_{len(cs)}")
        return {"status": "FAIL", "errors": errors, "continuity_count": len(cs)}
    params = cs[0]["params"]
    if "fvm_kernel_ownership" in params:
        errors.append("P1_MANUAL_OWNER_FLAG_FORBIDDEN")
    # The inherited PhysicsBase option disables automatic equation creation.
    # Historical binding-only fixtures still need it, but it MUST NEVER
    # certify a New-only ion cutover (even when explicitly set to false).
    if contract == "new-only" and "dont_create_kernels" in params:
        errors.append("P1_BINDING_ONLY_BYPASS_FORBIDDEN")
    fem, fvm = params.get("fem_species", "").split(), params.get("fvm_species", "").split()
    if not (fem or fvm) or len(set(fem + fvm)) != len(fem) + len(fvm):
        errors.append("P1_SPECIES_DUPLICATE_OR_EMPTY")
    species = mechanism.get("species", {})
    if not isinstance(species, dict):
        errors.append("P1_JSON_SPECIES_INVALID")
        species = {}
    for ident in fem + fvm:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", ident):
            errors.append("P1_SPECIES_INVALID_IDENTIFIER:" + ident)
        record = species.get(ident)
        if not isinstance(record, dict):
            errors.append("P1_JSON_SELECTED_SPECIES_MISSING:" + ident)
        else:
            density = record.get("initial_number_density")
            if isinstance(density, bool) or not isinstance(density, (float, int)) or not math.isfinite(density) or density <= 0:
                errors.append("P1_JSON_INITIAL_NUMBER_DENSITY_INVALID:" + ident)
            transport = record.get("transport_coef")
            modern = isinstance(transport, dict)
            model = transport.get("type") if modern else transport
            if model not in ("constant", "functor", "lookup"):
                errors.append("P1_JSON_TRANSPORT_MISSING_OR_INVALID:" + ident)
            elif modern:
                # Typed final-run JSON has one shared transport structure.
                # Canonical AD Functors are derived from species name.
                file = transport.get("file")
                unit = transport.get("unit")
                if model == "lookup":
                    if not isinstance(file, str) or not file.strip() or file == "none":
                        errors.append("P1_JSON_TRANSPORT_TABLE_MISSING:" + ident)
                    if unit not in ("reduced", "physical"):
                        errors.append("P1_JSON_TRANSPORT_UNIT_INVALID:" + ident)
                    if unit == "reduced":
                        plasmas = [b["params"] for b in blocks if b["name"] == "Plasmas"
                                   and b["parent"].endswith("Physics")]
                        if len(plasmas) != 1 or not all(
                            key in plasmas[0] for key in ("pressure", "temperature")
                        ):
                            errors.append("P1_ROOT_GAS_FUNCTORS_REQUIRED:" + ident)
                elif model == "functor":
                    if file != "none" or unit != "physical":
                        errors.append("P1_JSON_FUNCTOR_UNIT_OR_FILE_INVALID:" + ident)
                else:
                    if file != "none" or unit != "physical":
                        errors.append("P1_JSON_TRANSPORT_UNIT_INVALID:" + ident)
                    for key in ("mobility", "diffusivity"):
                        value = transport.get(key)
                        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                            errors.append(f"P1_JSON_TRANSPORT_COEFFICIENT_INVALID:{ident}:{key}")
            elif model == "constant":
                for key in ("mobility", "diffusivity"):
                    value = record.get(key)
                    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                        errors.append(f"P1_JSON_TRANSPORT_COEFFICIENT_INVALID:{ident}:{key}")
            elif model == "functor":
                if any(not isinstance(record.get(key), str) or not record[key].strip()
                       for key in ("mobility", "diffusivity")):
                    errors.append("P1_JSON_TRANSPORT_FUNCTOR_MISSING:" + ident)
            elif model == "lookup":
                if not isinstance(record.get("table_file"), str) or not record["table_file"].strip():
                    errors.append("P1_JSON_TRANSPORT_TABLE_MISSING:" + ident)
    canonical = {"log_" + ident: ident for ident in fvm}
    legacy = {old_name: ident for ident, old_name in LEGACY_S6_VARIABLES.items() if ident in fvm}
    tracked = {**canonical, **legacy}
    native = []
    for block in blocks:
        if block["parent"] not in ("FVKernels", "FVBCs"):
            continue
        variables = block["params"].get("variable", "").split()
        matched = [variable for variable in variables if variable in tracked]
        if matched:
            native.append({"file": block["file"], "line": block["line"],
                           "section": block["parent"], "name": block["name"],
                           "type": block["params"].get("type"),
                           "variable": " ".join(matched),
                           "species": [tracked[v] for v in matched]})
    # Ion FV equation cutover is independent of lower-D surface-charge
    # provenance. Retained Native wall-current sources are allowed when they
    # do not overlap a new C2-generated Functor/material owner. New C2 is
    # preferred when configured, but never forbid a disjoint Native producer
    # merely because its implementation is old.
    c2_ions = {
        ident for ident in fvm
        if isinstance(species.get(ident), dict) and (
            any(key in species[ident] for key in (
                "wall_molar_mass", "wall_sticking", "wall_ion_temperature_eV",
                "wall_use_element_gradient_for_potential"))
            or (
                ident != "e" and species[ident].get("charge_number", 0) != 0
                and isinstance(species[ident].get("transport_coef"), dict)
                and species[ident]["transport_coef"].get("type") != "none"
                and "molar_mass" in species[ident]
            )
        )
    }
    c2_current = bool(c2_ions) and bool(mechanism.get("ion_surface_current"))
    # New electron producer exists only in full DDEnergyEq (fem_potential).
    # In S6 ion-only cutover the Energy action is partial, so the existing
    # Native electron wall Flux may remain as the *sole* producer.
    canonical_electron_wall = bool(mechanism.get("drift_diffusion_boundaries")) and any(
        block["name"] == "Energy" and
        block["parent"].endswith("/DriftDiffusion") and
        bool(block["params"].get("fem_potential"))
        for block in blocks
    )
    # New grouped JSON creates the 4 electron particle + 4 electron
    # energy FEM BC objects as well. Their old Native BCs must be retired
    # from disposable Scratch even when the Native electron wall FLUX
    # Material remains the single flux producer.
    grouped_electron_bcs = bool(mechanism.get("drift_diffusion_boundaries"))
    historical_electron_bcs = {
        "PhysicsFEMLogMolarElectronFieldLimitedFluxBC",
        "PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC",
        "FEMElectronSheathBC", "FEMElectronEnergySheathBC",
    }
    duplicate_electron_bcs = [
        {"file": block["file"], "line": block["line"], "name": block["name"],
         "type": block["params"].get("type"), "variable": block["params"].get("variable")}
        for block in blocks
        if block["parent"] == "BCs" and (
            block["params"].get("type") in historical_electron_bcs or
            (
                block["params"].get("variable") in {
                    "log_ne", "log_e", "log_energy", "log_e_energy"
                } and (
                    "electron" in block["name"].lower() or
                    block["name"].startswith("e_")
                )
            )
        )
    ]
    generated_wall_names = {ident + "_wall" for ident in c2_ions}
    generated_wall_properties = {ident + "_wall_number_flux" for ident in c2_ions}
    current_names = {"cover_surface_current", "wafer_surface_current",
                     "focus_ring_surface_current"}
    current_outputs = {side + "_net_surface_current_density"
                       for side in ("cover", "wafer", "focus_ring")}
    wall_types = {"PhysicsIonWallTotalFluxMaterial",
                  "PhysicsIonWallFluxMaterial", "IonWallFluxMaterial"}
    old_wall_names = {"ion_wall_flux", "negative_ion_wall_flux",
                      "atomic_positive_ion_wall_flux"}
    explicit_functor = []
    producer_conflicts = []
    for block in blocks:
        if block["parent"] != "FunctorMaterials":
            continue
        params = block["params"]
        is_wall = (block["name"] in old_wall_names or
                   block["name"] in generated_wall_names or
                   params.get("type") in wall_types)
        is_electron_wall = (params.get("type") in {
            "ESWallFluxMaterial", "PhysicsElectronWallFluxMaterial",
            "PhysicsElectronAdjacentSheathWallFluxMaterial",
        } or block["name"] in {"electron_wall_flux", "e_wall_flux",
                               "electron_sheath_wall_flux"} or
            "e_wall_number_flux" in params.get("prop_names", "").split())
        is_current = (block["name"] in current_names or
                      params.get("property_name") in current_outputs)
        if not is_wall and not is_current and not is_electron_wall:
            continue
        owner = {"file": block["file"], "line": block["line"],
                 "name": block["name"], "type": params.get("type"),
                 "property_name": params.get("property_name"),
                 "family": "ion_wall" if is_wall else
                           "electron_wall" if is_electron_wall else "surface_current"}
        explicit_functor.append(owner)
        names = set(params.get("prop_names", "").split())
        conflict = ((canonical_electron_wall and is_electron_wall) or
                    block["name"] in generated_wall_names or
                    (params.get("type") in wall_types and
                     params.get("species_id") in c2_ions) or
                    bool(names & generated_wall_properties) or
                    (c2_current and (block["name"] in current_names or
                                      params.get("property_name") in current_outputs or
                                      bool(names & current_outputs))))
        if conflict:
            producer_conflicts.append(owner)
    if contract == "new-only":
        if producer_conflicts:
            errors.append(f"P1_GENERATED_C2_FUNCTOR_OWNER_COLLISION_{len(producer_conflicts)}")
        if native:
            errors.append(f"P1_NATIVE_FV_ION_OWNER_PRESENT_{len(native)}")
        if grouped_electron_bcs and duplicate_electron_bcs:
            errors.append(
                f"P1_NATIVE_ELECTRON_FEM_BC_OWNER_PRESENT_{len(duplicate_electron_bcs)}"
            )
        status = "P0_STATIC_PASS_ONLY"
    else:
        # This is a provenance-only S6-417/941 archived Native inventory.
        # It is NOT a successful New-only input and does not enable any C++ mode.
        if set(fvm) != set(LEGACY_S6_VARIABLES):
            errors.append("P1_LEGACY_S6_SPECIES_SET_MISMATCH")
        counts = {ident: {"FVKernels": 0, "FVBCs": 0} for ident in LEGACY_S6_VARIABLES}
        for obj in native:
            if len(obj["species"]) != 1:
                errors.append("P1_LEGACY_AMBIGUOUS_FV_VARIABLE:" + obj["name"])
                continue
            counts[obj["species"][0]][obj["section"]] += 1
        for ident in LEGACY_S6_VARIABLES:
            if counts[ident]["FVKernels"] != LEGACY_S6_KERNEL_COUNTS[ident]:
                errors.append("P1_LEGACY_KERNEL_COUNT_MISMATCH:" + ident)
            if counts[ident]["FVBCs"] != LEGACY_S6_BC_COUNTS[ident]:
                errors.append("P1_LEGACY_BC_COUNT_MISMATCH:" + ident)
        status = "P0_LEGACY_PROVENANCE_ONLY"
    return {"status": "FAIL" if errors else status, "contract": contract, "errors": errors,
            "fem_species": fem, "fvm_species": fvm, "native_fv_owner_count": len(native),
            "native_fv_owners": native,
            "explicit_ion_wall_current_owner_count": len(explicit_functor),
            "explicit_ion_wall_current_owners": explicit_functor,
            "c2_native_producer_collision_count": len(producer_conflicts),
            "c2_native_producer_collisions": producer_conflicts,
            "native_electron_bc_owner_count": len(duplicate_electron_bcs),
            "native_electron_bc_owners": duplicate_electron_bcs,
            "runtime_generated_kernel_bc_count": "NOT_VERIFIED_P0_ONLY"}

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--case", choices=("417", "941"), required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--contract", choices=CONTRACTS, default="new-only",
                        help="new-only rejects all Native ion FV owners; legacy-hybrid is provenance only")
    args = parser.parse_args(argv)
    prefix = f"S6_{args.case}/11_layers/"
    with zipfile.ZipFile(args.zip) as z:
        layers = {n.rsplit("/", 1)[-1]: z.read(n).decode("utf-8") for n in z.namelist()
                  if n.startswith(prefix) and n.endswith(".i")}
    if len(layers) != 11:
        parser.error(f"expected exactly 11 staged layers, got {len(layers)}")
    result = inspect(layers, json.loads(args.json.read_text()), contract=args.contract)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] in ("P0_STATIC_PASS_ONLY", "P0_LEGACY_PROVENANCE_ONLY") else 1


if __name__ == "__main__":
    sys.exit(main())
