"""Prepare a disposable S6 Chemistry candidate from already-staged C/D inputs.

This script does not solve, trigger P3, fetch private rates, or mutate a
historical archive. A caller must first stage the exact 10 original S6
layers plus migrated_continuity.i using the existing issue402 preparer,
canonicalize legacy state names, and remap retired FEM type names.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

PILOT = Path(__file__).resolve().parents[1]
COMMON = PILOT / "chemistry/oxygen_s6_common.json"

BASE_REMOVE = {
    "o2_elastic_400w_100us_dt1000ns_overlay.i": {
        "ei02_electron_energy_loss": ("log_energy", "elastic_energy_source_EI02")},
    "o_elastic_ei17_400w_100us_dt1000ns_overlay.i": {
        "ei17_electron_energy_exchange": ("log_energy", "S_electron_energy_EI17")},
    "issue477_S2-415_generation_overlay.i": {
        "ei415_electron_particle_source": ("log_e", "S_electron_molar_EI415"),
        "ei415_electron_energy_source": ("log_energy", "S_electron_energy_molar_EI415")},
    "issue477_S3-415-401_extra_overlay.i": {
        "ei401_electron_particle_sink": ("log_e", "S_electron_molar_EI401")},
}
VARIANT_REMOVE = {
    "417": {
        "issue477_S4-401-417_op_ionization_overlay.i": {
            "legacy8_h05_ei417_electron": ("log_e", "S_e_molar_EI417"),
            "legacy8_h05_ei417_electron_energy": ("log_energy", "S_energy_EI417")},
        "issue477_S5-417-407_o2_consumer_overlay.i": {
            "legacy8_407_electron_energy": ("log_energy", "S_energy_EI407")},
        "issue477_S6-417-407-2069-H25_EI2069_overlay.i": {
            "ei2069_electron_energy_sink": ("log_energy", "S_energy_EI2069")},
    },
    "941": {
        "issue477_S4-401-941_op_ionization_overlay.i": {
            "ei941_electron_particle_source": ("log_e", "S_electron_molar_EI941"),
            "ei941_electron_energy_source": ("log_energy", "S_electron_energy_molar_EI941")},
        "issue477_S5-941-407_o2_consumer_overlay.i": {
            "legacy8_407_electron_energy": ("log_energy", "S_energy_EI407")},
        "issue477_S6-941-407-2069-H25_EI2069_overlay.i": {
            "ei2069_electron_energy_sink": ("log_energy", "S_energy_EI2069")},
    },
}

# Only a two-level Kernels/name object without nested children can be retired.
# Require exact old owner, Functor, variable, RHS sign and plasma block.
KERNEL = re.compile(
    r"(?m)^  \[(?P<name>[A-Za-z0-9_]+)\][ \t]*\r?\n"
    r"(?P<body>(?:^    [^\r\n]*\r?\n)+)"
    r"^  \[\][ \t]*(?:\r?\n|$)"
)



# Wall renaming is a separate ownership-checked stage of the disposable D input.
# A name-only substitution without a verifiable Native FunctorMaterial producer
# is forbidden: it can silently change a BC or charge-ledger dependency.
_WALL_BLOCK = re.compile(
    r"(?m)^  \[(?P<name>[A-Za-z0-9_]+)\][ \t]*\r?\n"
    r"(?P<body>(?:^    [^\r\n]*\r?\n)+)"
    r"^  \[\][ \t]*(?:\r?\n|$)"
)
_WALL_TYPE = re.compile(r"(?m)^    type[ \t]*=[ \t]*(?P<type>[A-Za-z0-9_]+)[ \t]*$")
_WALL_PREFIX = re.compile(r"(?m)^    output_prefix[ \t]*=[ \t]*(?P<value>[^\r\n]*)\r?\n")
_WALL_KNOWN_LEGACY = {
    "ion_surface_number_flux", "ion_migration_number_flux",
    "ion_wall_number_flux", "ion_surface_mass_flux",
    "ion_migration_mass_flux", "ion_wall_mass_flux",
    "atomic_positive_ion_wall_number_flux",
    "atomic_positive_ion_wall_mass_flux",
    "negative_ion_wall_number_flux", "negative_ion_wall_mass_flux",
    "electron_wall_number_flux", "electron_mean_speed",
    "electron_sheath_drop_V",
}
_WALL_ION_PREFIX_TO_SPECIES = {
    "": "O2p",
    "atomic_positive_": "Op",
    "negative_": "Om",
}
# Only explicitly verified electron-density public Functors may underlie
# a canonical e_wall_* output. The historic S6 C input uses n_e_physical;
# synthetic per-species fixtures use n_e or e_number_density.
_WALL_ELECTRON_DENSITY_NAME_PROOF = {"n_e_physical", "n_e", "e_number_density"}
_WALL_DENSITY_NAME_PROOF = {
    "O2p": {"n_O2p", "n_i", "n_i_physical", "O2p_number_density",
            "ion_number_density_O2p"},
    "Op": {"n_Op", "n_op", "n_op_physical", "Op_number_density",
           "ion_number_density_Op", "atomic_positive_ion_number_density"},
    "Om": {"n_Om", "n_m", "n_m_physical", "Om_number_density",
           "ion_number_density_Om", "negative_ion_number_density"},
}


def canonicalize_staged_wall_inputs(edits: dict[Path, str]) -> tuple[dict[Path, str], dict]:
    """Rewrite scratch-only wall producers and all their consumers atomically.

    Every changed legacy name must have exactly one verified class owner.
    Unsupported old factories / ambiguous prefixes stop *before* file writes.
    This does not create new wall laws, coefficients, BCs or rate sources.
    """
    owners: dict[str, str] = {}
    owner_records = []
    updated = {}
    for path, contents in edits.items():
        blocks = list(_WALL_BLOCK.finditer(contents))
        for m in reversed(blocks):
            body = m.group("body")
            typed = _WALL_TYPE.search(body)
            if typed is None:
                continue
            material_type = typed.group("type")
            valid_types = {
                "PhysicsIonWallFluxMaterial", "PhysicsIonWallTotalFluxMaterial",
                "PhysicsElectronWallFluxMaterial",
                "PhysicsElectronAdjacentSheathWallFluxMaterial",
            }
            if material_type not in valid_types:
                continue
            # MOOSE wall materials are exclusively FunctorMaterials. Never
            # transform a similarly named block inside BC/Kernels sections.
            headings = re.findall(r"(?m)^\[([A-Za-z0-9_]+)\][ \t]*$", contents[:m.start()])
            if not headings or headings[-1] != "FunctorMaterials":
                raise ValueError("S6_WALL_MATERIAL_NOT_IN_FUNCTORMATERIALS: " + m.group("name"))
            if re.search(r"(?m)^    species_id\s*=", body):
                raise ValueError("S6_WALL_SPECIES_ID_ALREADY_SET: " + m.group("name"))

            pairs: dict[str, str] = {}
            prefix_match = _WALL_PREFIX.search(body)
            prefix = prefix_match.group("value").strip().strip(chr(39) + chr(34)) if prefix_match else ""
            if material_type == "PhysicsIonWallFluxMaterial":
                if m.group("name") not in ("ion_wall_flux", "O2p_wall_flux"):
                    raise ValueError("S6_WALL_ION_OWNER_AMBIGUOUS: " + m.group("name"))
                if prefix_match:
                    raise ValueError("S6_WALL_ION_MATERIAL_CANNOT_HAVE_PREFIX")
                species = "O2p"
                pairs = {
                    "ion_surface_number_flux": "O2p_wall_surface_number_flux",
                    "ion_migration_number_flux": "O2p_wall_migration_number_flux",
                    "ion_wall_number_flux": "O2p_wall_number_flux",
                    "ion_surface_mass_flux": "O2p_wall_surface_mass_flux",
                    "ion_migration_mass_flux": "O2p_wall_migration_mass_flux",
                    "ion_wall_mass_flux": "O2p_wall_mass_flux",
                }
            elif material_type == "PhysicsIonWallTotalFluxMaterial":
                if prefix not in _WALL_ION_PREFIX_TO_SPECIES:
                    raise ValueError("S6_WALL_UNRECOGNIZED_OUTPUT_PREFIX: " + prefix)
                species = _WALL_ION_PREFIX_TO_SPECIES[prefix]
                pairs = {
                    prefix + "ion_wall_number_flux": species + "_wall_number_flux",
                    prefix + "ion_wall_mass_flux": species + "_wall_mass_flux",
                }
                if prefix_match:
                    body = body[:prefix_match.start()] + body[prefix_match.end():]
            else:
                if m.group("name") != "electron_wall_flux":
                    raise ValueError("S6_WALL_ELECTRON_OWNER_AMBIGUOUS: " + m.group("name"))
                if prefix_match:
                    raise ValueError("S6_WALL_ELECTRON_PREFIX_UNSUPPORTED")
                species = "e"
                pairs = {
                    "electron_mean_speed": "e_mean_speed",
                    "electron_wall_number_flux": "e_wall_number_flux",
                }
                if material_type == "PhysicsElectronAdjacentSheathWallFluxMaterial":
                    pairs["electron_sheath_drop_V"] = "e_wall_sheath_drop_V"
            if species != "e":
                # An output prefix is not proof of the *physical species* it
                # evaluates. Preserve the original density input exactly, but
                # require a predeclared species-specific source identity.
                density_field = re.search(
                    r"(?m)^    ion_number_density[ \t]*=[ \t]*([A-Za-z0-9_]+)[ \t]*$", body)
                observed_density = density_field.group(1) if density_field else ""
                if observed_density not in _WALL_DENSITY_NAME_PROOF[species]:
                    raise ValueError("S6_WALL_DENSITY_IDENTITY_UNPROVED: " +
                                     species + " <- " + observed_density)
                charge_field = re.search(
                    r"(?m)^    charge_number[ \t]*=[ \t]*([+-]?(?:1|1\.0))[ \t]*$", body)
                expected_charge = -1 if species == "Om" else 1
                if not charge_field or float(charge_field.group(1)) != expected_charge:
                    raise ValueError("S6_WALL_CHARGE_IDENTITY_UNPROVED: " + species)
            else:
                electron_density_field = re.search(
                    r"(?m)^    electron_density[ \t]*=[ \t]*([A-Za-z0-9_]+)[ \t]*$",
                    body)
                observed_electron_density = (
                    electron_density_field.group(1) if electron_density_field else "")
                if observed_electron_density not in _WALL_ELECTRON_DENSITY_NAME_PROOF:
                    raise ValueError(
                        "S6_WALL_ELECTRON_DENSITY_IDENTITY_UNPROVED: " +
                        observed_electron_density)
            for old, canonical in pairs.items():
                if old in owners:
                    raise ValueError("S6_WALL_DUPLICATE_OUTPUT_OWNER: " + old)
                if canonical in owners.values():
                    raise ValueError("S6_WALL_DUPLICATE_CANONICAL_OUTPUT: " + canonical)
                owners[old] = canonical
            # The old total-flux class was retired upstream (#523). Its
            # surface+migration total number/mass law and all input parameters
            # are implemented by PhysicsIonWallFluxMaterial. This is only a
            # staged *type/identity* migration, never a new wall equation.
            # Validate the known old factory before installing its replacement.
            if material_type == "PhysicsIonWallTotalFluxMaterial":
                body, converted = _WALL_TYPE.subn(
                    "    type = PhysicsIonWallFluxMaterial", body, count=1)
                if converted != 1:
                    raise ValueError("S6_WALL_RETIRED_TYPE_CUTOVER_FAILED")
            # Add only the output-selector option; no physical input is altered.
            type_line = _WALL_TYPE.search(body)
            assert type_line is not None
            body = body[:type_line.end()] + "\n    species_id = " + species + body[type_line.end():]
            contents = contents[:m.start("body")] + body + contents[m.end("body"):]
            owner_records.append({
                "source_layer": path.name, "block": m.group("name"),
                "source_type": material_type,
                "type": "PhysicsIonWallFluxMaterial"
                if material_type == "PhysicsIonWallTotalFluxMaterial" else material_type,
                "species_id": species,
                "outputs": dict(sorted(pairs.items())),
            })
        updated[path] = contents

    # A selected consumer must never point to a renamed, unowned old output.
    # This also catches unsupported QPX/retired wall producers in historical
    # input layers rather than pretending a string edit established parity.
    counts = {old: 0 for old in _WALL_KNOWN_LEGACY}
    for text in updated.values():
        for old in counts:
            counts[old] += len(re.findall(
                r"(?<![A-Za-z0-9_])" + re.escape(old) + r"(?![A-Za-z0-9_])", text))
    missing = sorted(old for old, count in counts.items() if count and old not in owners)
    if missing:
        raise ValueError("S6_WALL_UNVERIFIED_LEGACY_OUTPUT_OWNER: " + ", ".join(missing))

    substitutions = {name: 0 for name in owners}
    for path, contents in updated.items():
        for old, canonical in sorted(owners.items(), key=lambda item: -len(item[0])):
            pattern = r"(?<![A-Za-z0-9_])" + re.escape(old) + r"(?![A-Za-z0-9_])"
            contents, number = re.subn(pattern, canonical, contents)
            substitutions[old] += number
        updated[path] = contents
    # No scratch input may retain the retired total-flux factory type.
    if any(re.search(
            r"(?m)^    type[ \t]*=[ \t]*PhysicsIonWallTotalFluxMaterial[ \t]*$",
            contents) for contents in updated.values()):
        raise ValueError("S6_WALL_RETIRED_TYPE_STILL_PRESENT")
    # Stage one can be a no-op only if no old wall outputs are actually used.
    return updated, {
        "status": "SCRATCH_ONLY_SPECIES_WALL_NAMES" if owners else "NO_LEGACY_WALL_OUTPUTS",
        "wall_material_owners": list(reversed(owner_records)),
        "owner_count": len(owner_records),
        "consumer_and_reference_replacements": {
            old: n for old, n in sorted(substitutions.items()) if n
        },
        "P3": "NOT_RUN", "science": "SCIENCE_HOLD",
    }


def sha(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()



# Archived S6-417/941 B/C use this one electron lookup Material in the first
# (shared) input layer. Fail-closed conversion applies to ephemeral D scratch
# only: the historical B/C archive, lookup table, mean-energy Functor and
# 5/3 energy projection all remain the same.
_ARCHIVED_ELECTRON_LOOKUP = {
    "type": "PhysicsElectronTransportLookupMaterial",
    "property_table_file": "'../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'",
    "mean_energy": "mean_en_solved",
    "pressure": "p",
    "gas_temperature": "T_g_fixed",
    "bounds_policy": "clamp",
    "block": "plasma",
}



def _parse_exact_s6_owner_parameters(body: str, owner: str) -> dict[str, str]:
    """Fail closed on ALL non-comment content, including extra-indented lines.

    Historical S6 owner blocks use exactly four leading spaces for each
    assignment. Unknown or hidden assignments must never be silently dropped
    when serializing a replacement owner.
    """
    params = {}
    for line in body.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(
            r"    ([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*([^\r\n]+)", line)
        if not match:
            raise ValueError("S6_OWNER_UNPARSED_LINE: " + owner + " " + repr(line))
        key, value = match.group(1), match.group(2).strip()
        if key in params:
            raise ValueError("S6_OWNER_DUPLICATE_PARAMETER: " + owner + " " + key)
        params[key] = value
    return params

def canonicalize_staged_electron_lookup(
        edits: dict[Path, str]) -> tuple[dict[Path, str], dict]:
    """Migrate exactly one verified historical electron closure, with no physics edits."""
    candidates = []
    for path, source in edits.items():
        for m in _WALL_BLOCK.finditer(source):
            body = m.group("body")
            typed = _WALL_TYPE.search(body)
            material_type = typed.group("type") if typed else ""
            if m.group("name") != "electron_transport" and (
                    material_type != "PhysicsElectronTransportLookupMaterial"):
                continue
            headings = re.findall(
                r"(?m)^\[([A-Za-z0-9_]+)\][ \t]*$", source[:m.start()])
            if not headings or headings[-1] != "FunctorMaterials":
                raise ValueError("S6_ELECTRON_LOOKUP_NOT_FUNCTORMATERIAL")
            values = _parse_exact_s6_owner_parameters(body, "electron_transport")
            if values != _ARCHIVED_ELECTRON_LOOKUP:
                raise ValueError(
                    "S6_ELECTRON_LOOKUP_IDENTITY_UNPROVED: " + path.name +
                    " " + repr(values))
            candidates.append((path, source, m))
    if len(candidates) != 1:
        raise ValueError(
            "S6_ELECTRON_LOOKUP_OWNER_COUNT_UNPROVED: " + str(len(candidates)))
    path, source, m = candidates[0]
    table_path = _ARCHIVED_ELECTRON_LOOKUP["property_table_file"]
    # Exactly the same table/pressure/temperature, same 'clamp' policy, and
    # DDMaterial's hardwired mean_en_solved lookup axis. No synthetic values.
    new_body = (
        "    type = DDMaterial\n"
        "    species_id = e\n"
        "    model = lookup\n"
        "    table_file = " + table_path + "\n"
        "    table_units = reduced\n"
        "    pressure = p\n"
        "    gas_temperature = T_g_fixed\n"
        "    bounds_policy = clamp\n"
        "    fluid_energy = true\n"
        "    block = plasma\n"
    )
    revised = source[:m.start("body")] + new_body + source[m.end("body"):]
    results = dict(edits)
    results[path] = revised
    return results, {
        "status": "SCRATCH_ONLY_EXACT_ELECTRON_LOOKUP_CUTOVER",
        "source_layer": path.name,
        "owner": "electron_transport",
        "from_type": "PhysicsElectronTransportLookupMaterial",
        "to_type": "DDMaterial",
        "table_file": table_path,
        "coordinate": "mean_en_solved",
        "pressure": "p",
        "gas_temperature": "T_g_fixed",
        "table_units": "reduced",
        "bounds_policy": "clamp",
        "fluid_energy": True,
        "original_block_sha256": sha(m.group(0).encode("utf-8")),
        "migrated_block_sha256": sha(
            (m.group(0)[:m.start("body") - m.start()] + new_body +
             m.group(0)[m.end("body") - m.start():]).encode("utf-8")),
        "P2": "NOT_RUN",
        "P3": "NOT_RUN",
        "science": "SCIENCE_HOLD",
    }



def remove_one(text: str, name: str, variable: str, functor: str) -> str:
    # Native layer names may be reused by a FunctorMaterial and its Kernel.
    # Match ONLY the old FunctorKernel owner in the [Kernels] root section.
    match_list = [
        m for m in KERNEL.finditer(text)
        if m.group("name") == name and
        re.search(r"(?m)^\s*type\s*=\s*FunctorKernel\s*$", m.group("body"))
    ]
    if len(match_list) != 1:
        raise ValueError(f"{name}: expected one old FunctorKernel, found {len(match_list)}")
    m = match_list[0]
    prefix = text[:m.start()]
    sections = re.findall(r"(?m)^\[([A-Za-z0-9_]+)\][ \t]*$", prefix)
    if not sections or sections[-1] != "Kernels":
        raise ValueError(f"{name}: owner not inside [Kernels]")
    body = m.group("body")
    required = (
        "type = FunctorKernel",
        f"variable = {variable}",
        f"functor = {functor}",
        "functor_on_rhs = true",
        "block = plasma",
    )
    for line in required:
        if not re.search(r"(?m)^\s*" + re.escape(line) + r"\s*$", body):
            raise ValueError(f"{name}: source/sign owner differs: {line}")
    return text[:m.start()] + text[m.end():]


def prepare(staged_chem_dir: Path, ordered: list[str], variant: str) -> dict:
    """Mutate ONLY staged scratch files; originals and physics rates are untouched."""
    if variant not in VARIANT_REMOVE:
        raise ValueError("Expected S6 variant 417 or 941")
    if len(ordered) != 11 or Path(ordered[-1]).name != "migrated_continuity.i":
        raise ValueError("Expected 10 original layers followed by migrated_continuity.i")
    existing = {Path(item).name for item in ordered}
    removals = dict(BASE_REMOVE, **VARIANT_REMOVE[variant])
    if set(removals) - existing:
        raise ValueError("S6 layers incomplete: " + str(sorted(set(removals)-existing)))
    staged_chem_dir = Path(staged_chem_dir).resolve()
    overlay = staged_chem_dir / "migrated_continuity.i"
    if not overlay.is_file():
        raise ValueError("Expected scratch migration overlay")
    if not all((staged_chem_dir / Path(item).name).is_file() for item in ordered):
        raise ValueError("Missing staged S6 layer")
    # Validate and construct every modified layer before any file writes.
    edits = {}
    retired = []
    for basename, owners in removals.items():
        target = staged_chem_dir / basename
        source = target.read_text(encoding="utf-8")
        for kernel_name, (variable, functor) in owners.items():
            source = remove_one(source, kernel_name, variable, functor)
            retired.append(kernel_name)
        edits[target] = source
    if len(retired) != 9:
        raise ValueError("Expected exactly nine old electron particle/energy Kernels")
    # Retain original owner signatures above (log_energy), then consistently
    # migrate the remaining scratch-only variable references to the new
    # internally resolved DDEnergyEq state: log_e_energy.
    # Rename all ten staged layers, not only the nine edited sources,
    # so native RF/Joule and Material couplings resolve the same state.
    canonical_names = {
        "log_energy": "log_e_energy",
        "R_elastic_O2": "R_EI02",
        "R_elastic_O": "R_EI17",
        "R_ion_O2": "R_EI415",
    }
    renamed = {name: 0 for name in canonical_names}
    for item in ordered[:-1]:
        target = staged_chem_dir / Path(item).name
        source = edits.get(target, target.read_text(encoding="utf-8"))
        for old, new in canonical_names.items():
            pattern = r"(?<![A-Za-z0-9_])" + re.escape(old) + r"(?![A-Za-z0-9_])"
            source, count = re.subn(pattern, new, source)
            renamed[old] += count
        edits[target] = source
    # The new run must use canonical names from the actual rate producers,
    # not alias Materials. Reject a missing legacy owner before writing scratch.
    missing = [name for name in ("R_elastic_O2", "R_elastic_O", "R_ion_O2")
               if renamed[name] == 0]
    if missing:
        raise ValueError("Expected original S6 progress providers: " + ", ".join(missing))
    template = (PILOT / f"s6_{variant}_chemistry_run.template.i").read_text()
    common = COMMON.read_bytes()
    selected = (PILOT / f"chemistry/oxygen_s6_{variant}.json").read_bytes()
    expected = {
        "EI-417" if variant == "417" else "EI-941"
    }
    variant_doc = json.loads(selected)
    if set(variant_doc["equations"]) != expected:
        raise ValueError("Wrong reaction-set branch for S6")
    if "files = 'chemistry/oxygen_s6_common.json chemistry/oxygen_s6_" + variant + ".json'" not in template:
        raise ValueError("Template does not bind correct mechanism files")
    # New-run Wall names are cut over only when every legacy output has a
    # verified, uniquely identified FunctorMaterial producer. Fail before
    # mutating any scratch file if an old/unknown wall owner is still present.
    edits, lookup_cutover = canonicalize_staged_electron_lookup(edits)
    edits, wall_cutover = canonicalize_staged_wall_inputs(edits)
    # Only after every owner check passes, modify disposable scratch.
    dest = staged_chem_dir / "chemistry"
    dest.mkdir(parents=True, exist_ok=True)
    for target, updated in edits.items():
        target.write_text(updated, encoding="utf-8")
    overlay.write_text(template, encoding="utf-8")
    (dest / "oxygen_s6_common.json").write_bytes(common)
    (dest / f"oxygen_s6_{variant}.json").write_bytes(selected)
    return {
        "status": "P2_INPUT_PREPARED",
        "variant": variant,
        "removed_legacy_kernel_names": sorted(retired),
        "removed_count": len(retired),
        "canonical_name_replacements": renamed,
        "scratch_electron_lookup_cutover": lookup_cutover,
        "scratch_wall_functor_cutover": wall_cutover,
        "overlay_sha256": sha(template.encode()),
        "common_mechanism_sha256": sha(common),
        "variant_mechanism_sha256": sha(selected),
        "run": "NOT_RUN",
        "native_check_input": "NOT_RUN",
        "science": "SCIENCE_HOLD"
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged-chem-dir", type=Path, required=True)
    parser.add_argument("--ordered-file", type=Path, required=True,
                        help="JSON list of 10 S6 layer paths + migrated_continuity.i")
    parser.add_argument("--variant", choices=("417", "941"), required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    ordered = json.loads(args.ordered_file.read_text())
    report = prepare(args.staged_chem_dir, ordered, args.variant)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
