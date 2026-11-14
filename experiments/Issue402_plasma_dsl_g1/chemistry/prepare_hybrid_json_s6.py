"""Scratch-only canonical S6 hybrid: JSON owns electron DD/energy state,
electron sheath BCs and kinetic reaction providers. Historical Native .i
owns RF, Poisson, ion equations, neutral transport and all other wall BCs.

Invoke AFTER the existing source-identity-checked Chemistry.prepare() on
disposable, staged 11-layer S6 inputs. No archived source is ever edited.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

N_A = 6.02214076e23
ROOT = Path(__file__).resolve().parents[1]
VAR_NAMES = ("log_e", "log_O2p", "log_Om", "log_Op", "log_e_energy")
# Only the disposable Native input is migrated. The historical source
# material still provides exactly the same physical coefficients; old names
# are never published in the active hybrid configuration.
NATIVE_COEFFICIENT_RENAME = {
    "ion_mobility": "O2p_mobility",
    "ion_diffusion": "O2p_diffusivity",
    "negative_ion_mobility": "Om_mobility",
    "negative_ion_diffusion": "Om_diffusivity",
    "atomic_positive_ion_mobility": "Op_mobility",
    "atomic_positive_ion_diffusion": "Op_diffusivity",
}
ARCHIVED_COEFFICIENT_CONSTANTS = {
    "type": "ADGenericFunctorMaterial",
    "prop_names": ("'p_fixed T_g_fixed ion_mobility ion_diffusion "
                   "negative_ion_mobility negative_ion_diffusion "
                   "atomic_positive_ion_mobility atomic_positive_ion_diffusion "
                   "carrier_one'"),
    "prop_values": ("'1.333223684 300 10 0.25851999786435537 "
                    "10 0.25851999786435537 10 0.25851999786435537 1.0'"),
    "block": "plasma",
}
# Exactly the archived common 400-W initial state, after name-only
# canonicalization; never invent new numerical initial conditions.
PINNED_INITIAL_LOG = {
    "log_e": "-20.216123548032986",
    "log_O2p": "-20.216123548032986",
    "log_Om": "-27.123878827015126",
    "log_Op": "-27.123878827015126",
    "log_e_energy": "-18.829829186913098",
}
BLOCK = re.compile(
    r"(?m)^  \[(?P<name>[A-Za-z0-9_]+)\][ \t]*\r?\n"
    r"(?P<body>(?:^    [^\r\n]*\r?\n)+)"
    r"^  \[\][ \t]*(?:\r?\n|$)"
)
SOURCE_MATERIAL = {
    "mean_energy": {
        "type": "ElectronEnergyMaterial",
        "electron_energy_density": "log_e_energy",
        "electron_density": "log_e",
        "state_form": "log_molar_eV",
        "block": "plasma",
    },
    "electron_transport": {
        "type": "DDTransportMaterial",
        "species_id": "e",
        "model": "lookup",
        "table_file": "'../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'",
        "table_units": "reduced",
        "pressure": "p",
        "gas_temperature": "T_g_fixed",
        "bounds_policy": "clamp",
        "fluid_energy": "true",
        "block": "plasma",
    },
    "electron_physical_density": {
        "type": "ADParsedFunctorMaterial",
        "property_name": "n_e_physical",
        "functor_names": "'electron_molar_density'",
        "functor_symbols": "'ce'",
        "expression": "'6.02214076e23*ce'",
        "block": "plasma",
    },
    "electron_wall_flux": {
        "type": "ESWallFluxMaterial",
        "species_id": "e",
        "electron_density": "n_e_physical",
        "mean_energy": "e_energy_eV",
        "sticking": "1.0",
        "block": "plasma",
        "potential": "potential",
        "use_element_gradient_for_potential": "true",
    },
}
SOURCE_KERNEL = {
    "energy_time": {
        "type": "FEMLogMolarTimeDerivative",
        "variable": "log_e_energy",
        "block": "plasma",
    },
    "energy_transport": {
        "type": "FEMLogMolarDriftDiffusion",
        "variable": "log_e_energy",
        "potential": "potential",
        "mobility": "electron_energy_mobility",
        "diffusion": "electron_energy_diffusion",
        "charge_number": "-1",
        "block": "plasma",
    },
    "energy_joule": {
        "type": "FEMLogMolarElectronJouleHeating",
        "variable": "log_e_energy",
        "electron_log_density": "log_e",
        "potential": "potential",
        "mobility": "electron_mobility",
        "diffusion": "electron_diffusion",
        "block": "plasma",
    },
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parameters(body: str) -> dict[str, str]:
    output: dict[str, str] = {}
    for line in body.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"    ([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.+)", line)
        if not match or match.group(1) in output:
            raise ValueError("HYBRID_UNKNOWN_OR_DUPLICATE_OWNER_PARAMETER: " + repr(line))
        output[match.group(1)] = match.group(2).strip()
    return output


def retire(source: str, section: str, name: str, expected: dict[str, str]
           ) -> tuple[str, dict]:
    matches = []
    for match in BLOCK.finditer(source):
        if match.group("name") != name:
            continue
        roots = re.findall(r"(?m)^\[([A-Za-z0-9_]+)\]\s*$", source[:match.start()])
        if roots and roots[-1] == section:
            matches.append(match)
    if len(matches) != 1:
        raise ValueError(f"HYBRID_OWNER_COUNT_{section}_{name}: {len(matches)}")
    m = matches[0]
    got = parameters(m.group("body"))
    if got != expected:
        raise ValueError(f"HYBRID_OWNER_IDENTITY_{section}_{name}: {got}")
    return (source[:m.start()] + source[m.end():], {
        "section": section, "name": name,
        "old_block_sha256": digest(m.group(0).encode("utf-8")),
        "old_parameters": got,
    })



# Preserve the exact original eight FEM BC identities and sideset groups,
# but give construction ownership to DriftDiffusion via unified JSON.
# Only disposable scratch input loses these verified legacy operator blocks.
SHEATH_BC_SPEC = {
    "electron_sheath": ("FEMElectronSheathBC",
                        "'plasma_electrode plasma_metal plasma_right'"),
    "electron_cover_dielectric": ("FEMElectronSheathBC", "'plasma_cover'"),
    "electron_wafer_dielectric": ("FEMElectronSheathBC", "'plasma_wafer'"),
    "electron_focus_ring_dielectric": ("FEMElectronSheathBC",
                                       "'plasma_focus_ring'"),
    "electron_energy_sheath": ("FEMElectronEnergySheathBC",
                               "'plasma_electrode plasma_metal plasma_right'"),
    "electron_energy_cover": ("FEMElectronEnergySheathBC", "'plasma_cover'"),
    "electron_energy_wafer": ("FEMElectronEnergySheathBC", "'plasma_wafer'"),
    "electron_energy_focus_ring": ("FEMElectronEnergySheathBC",
                                   "'plasma_focus_ring'"),
}
OLD_SHEATH_TYPES = {
    "FEMElectronSheathBC": "PhysicsFEMLogMolarElectronFieldLimitedFluxBC",
    "FEMElectronEnergySheathBC":
        "PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC",
}


def migrate_exact_s6_fem_sheath(source: str) -> tuple[str, list[dict]]:
    """Guarded 4+4 BC relocation into JSON, scratch S6 D input only.

    Every former BC operator is checked against the archived identity before
    it is removed from scratch. DriftDiffusion creates the exact same BCs.
    """
    matched = []
    for name, (new_type, boundary) in SHEATH_BC_SPEC.items():
        candidates = []
        for match in BLOCK.finditer(source):
            if match.group("name") != name:
                continue
            roots = re.findall(
                r"(?m)^\[([A-Za-z0-9_]+)\]\s*$", source[:match.start()])
            if roots and roots[-1] == "BCs":
                candidates.append(match)
        if len(candidates) != 1:
            raise ValueError(
                f"HYBRID_SHEATH_BC_OWNER_COUNT_{name}: {len(candidates)}")
        old = candidates[0]
        expected = {
            "type": OLD_SHEATH_TYPES[new_type],
            "variable": ("log_e_energy" if new_type == "FEMElectronEnergySheathBC"
                         else "log_e"),
            "wall_number_flux": "e_wall_number_flux",
            "boundary": boundary,
        }
        if new_type == "FEMElectronEnergySheathBC":
            expected["mean_energy"] = "e_energy_eV"
        got = parameters(old.group("body"))
        if got != expected:
            raise ValueError(
                "HYBRID_SHEATH_BC_IDENTITY_" + name + ": " + repr(got))
        matched.append((old, name, new_type))
    if len(matched) != 8:
        raise ValueError("HYBRID_EXPECTED_EXACTLY_8_REGISTERED_SHEATH_BCS")
    report = []
    for old, name, new_type in reversed(matched):
        before = old.group(0)
        source = source[:old.start()] + source[old.end():]
        report.append({
            "owner": name, "new_type": new_type,
            "old_block_sha256": digest(before.encode("utf-8")),
            "new_owner": "DriftDiffusion JSON",
        })
    if "PhysicsFEMLogMolarElectronFieldLimitedFluxBC" in source or (
        "PhysicsFEMLogMolarElectronEnergyFieldLimitedFluxBC" in source
    ):
        raise ValueError("HYBRID_UNREGISTERED_SHEATH_BC_REMAINS")
    return source, sorted(report, key=lambda x: x["owner"])


 
def canonicalize_native_ion_transport_sources(
    layered: dict[str, str], base_name: str
) -> tuple[dict[str, str], dict]:
    """Rename both coefficient producers and consumers; never change values.

    Strictly verify the one original Native source Material before any write.
    Each mutation is one-to-one lexical substitution in scratch input files.
    """
    original_base = layered[base_name]
    matches = []
    for block in BLOCK.finditer(original_base):
        if block.group("name") != "constants":
            continue
        roots = re.findall(
            r"(?m)^\[([A-Za-z0-9_]+)\]\s*$", original_base[:block.start()])
        if roots and roots[-1] == "FunctorMaterials":
            matches.append(block)
    if len(matches) != 1 or parameters(matches[0].group("body")) != (
        ARCHIVED_COEFFICIENT_CONSTANTS
    ):
        raise ValueError("HYBRID_NATIVE_ION_CONSTANTS_SIGNATURE_CHANGED")
    original_hash = digest(matches[0].group(0).encode("utf-8"))
    counts = {old: 0 for old in NATIVE_COEFFICIENT_RENAME}
    updated = {}
    touched = []
    for filename, source in layered.items():
        old_source = source
        for old_name, new_name in NATIVE_COEFFICIENT_RENAME.items():
            source, count = re.subn(
                r"(?<![A-Za-z0-9_])" + re.escape(old_name) +
                r"(?![A-Za-z0-9_])", new_name, source
            )
            counts[old_name] += count
        for old_name in NATIVE_COEFFICIENT_RENAME:
            if re.search(r"(?<![A-Za-z0-9_])" + re.escape(old_name) +
                         r"(?![A-Za-z0-9_])", source):
                raise ValueError("HYBRID_UNMIGRATED_NATIVE_COEFFICIENT_" + old_name)
        updated[filename] = source
        if source != old_source:
            touched.append(filename)
    # Every original constant is published exactly once and consumed by at
    # least the corresponding Native wall/transport operator.
    if any(count < 2 for count in counts.values()):
        raise ValueError("HYBRID_MISSING_NATIVE_COEFFICIENT_CONSUMER")
    expected_props = ARCHIVED_COEFFICIENT_CONSTANTS["prop_names"]
    for old_name, new_name in NATIVE_COEFFICIENT_RENAME.items():
        # Token boundaries matter: ion_mobility is a suffix of
        # negative_ion_mobility and atomic_positive_ion_mobility.
        expected_props = re.sub(
            r"(?<![A-Za-z0-9_])" + re.escape(old_name) +
            r"(?![A-Za-z0-9_])", new_name, expected_props
        )
    migrated = [
        block for block in BLOCK.finditer(updated[base_name])
        if block.group("name") == "constants"
    ]
    if len(migrated) != 1 or parameters(migrated[0].group("body")) != {
        **ARCHIVED_COEFFICIENT_CONSTANTS, "prop_names": expected_props
    }:
        raise ValueError("HYBRID_NATIVE_ION_CONSTANTS_VALUE_OR_OWNER_CHANGED")
    return updated, {
        "old_to_species_names": NATIVE_COEFFICIENT_RENAME,
        "substitution_counts": counts,
        "changed_staged_native_layers": sorted(touched),
        "archived_constants_block_sha256": original_hash,
        "canonical_constants_block_sha256":
            digest(migrated[0].group(0).encode("utf-8")),
        "constant_values_unchanged": True,
        "physics_equations_unchanged": True,
    }


# The only user-configured gas values are in [Physics]/[Plasmas].
# These historical constants are checked exactly before they are retired.

def retire_staged_kinetic_owners(edits: dict[str, str], mechanism: dict) -> tuple[dict[str, str], dict]:
    """Retire only source-verified progress and elastic-loss producers in scratch.

    No rate tables are copied or synthesized. The JSON table path names point
    to independently staged original files; Physics Chemistry creates the
    original Native Material classes. Archive source bytes are untouched.
    """
    expected = {}
    for reaction in mechanism["reactions"]:
        id = reaction["id"]
        progress = ("R_EI" + id[3:] if id.startswith("EI-") else "R_H" + id[1:])
        expected[progress] = reaction
    elastic = {"delta_epsilon_EI02_eV", "delta_epsilon_EI17_eV"}
    seen = {}
    removed = []
    updated = dict(edits)

    for filename, original in edits.items():
        source = original
        candidates = []
        for block in BLOCK.finditer(original):
            headings = re.findall(r"(?m)^\[([A-Za-z0-9_]+)\]\s*$",
                                  original[:block.start()])
            if not headings or headings[-1] != "FunctorMaterials":
                continue
            args = parameters(block.group("body"))
            progress = args.get("reaction_progress", "")
            if not progress and args.get("property_name") in expected:
                progress = args["property_name"]
            if progress in expected:
                if progress in seen:
                    raise ValueError("HYBRID_DUPLICATE_NATIVE_RATE_OWNER_" + progress)
                reaction = expected[progress]
                if "table" in reaction:
                    # Scratch archives contain both the retired RateCoeffMaterial
                    # spelling and the active EIRateCoefMaterial. Verify, then
                    # remove the historical owner; never register an alias.
                    if args.get("type") not in {"RateCoeffMaterial", "EIRateCoefMaterial"}:
                        raise ValueError("HYBRID_RATE_FACTORY_CHANGED_" + progress)
                    actual = args.get("rate_table_file", "").strip().strip("'").strip('"')
                    if actual != reaction["table"]:
                        # Same basename in a different directory is not proof
                        # of the same physical lookup or dimensional basis.
                        raise ValueError("HYBRID_RATE_TABLE_IDENTITY_CHANGED_" + progress)
                    if (args.get("mean_energy") != "e_energy_eV" or
                            args.get("electron_number_density") != "n_e_physical" or
                            not args.get("target_molar_concentration")):
                        raise ValueError("HYBRID_NATIVE_RATE_INPUT_CHANGED_" + progress)
                elif reaction["id"] == "H25":
                    if (args.get("type") != "ADParsedFunctorMaterial" or
                            "1.204428152e7" not in args.get("expression", "") or
                            "(300.0/tg)^0.4" not in args.get("expression", "")):
                        raise ValueError("HYBRID_H25_NATIVE_LAW_MISMATCH")
                else:
                    raise ValueError("HYBRID_UNKNOWN_NON_TABLE_REACTION_" + progress)
                seen[progress] = filename
                candidates.append((block, progress))
            elif args.get("property_name") in elastic:
                name = args["property_name"]
                if name in seen:
                    raise ValueError("HYBRID_DUPLICATE_ELASTIC_ENERGY_OWNER_" + name)
                if (args.get("type") != "ADParsedFunctorMaterial" or
                        "e_energy_eV" not in args.get("functor_names", "") or
                        "temperature" not in args.get("functor_names", "") or
                        "(2.0/3.0)*eps" not in args.get("expression", "")):
                    raise ValueError("HYBRID_ELASTIC_SOURCE_IDENTITY_CHANGED_" + name)
                seen[name] = filename
                candidates.append((block, name))
        for block, owner in reversed(candidates):
            source = source[:block.start()] + source[block.end():]
            removed.append({"owner": owner, "source_layer": filename,
                            "source_sha256": digest(block.group(0).encode("utf-8"))})
        updated[filename] = source
    missing_rate = sorted(set(expected) - set(seen))
    missing_elastic = sorted(elastic - set(seen))
    # A full S6 migration must prove removal of all eight historical R_k
    # owners and both historical elastic-loss Functors, not just a subset.
    if missing_rate:
        raise ValueError("HYBRID_INCOMPLETE_NATIVE_RATE_OWNER_CUTOVER: " +
                         ", ".join(missing_rate))
    if missing_elastic:
        raise ValueError("HYBRID_INCOMPLETE_NATIVE_ELASTIC_OWNER_CUTOVER: " +
                         ", ".join(missing_elastic))
    return updated, {
        "native_kinetic_owners_retired": sorted(removed, key=lambda r: r["owner"]),
        "native_progress_retired_count": sum(k in seen for k in expected),
        "elastic_loss_retired_count": sum(k in seen for k in elastic),
        "original_rate_tables_unchanged": True,
    }


ROOT_PRESSURE_PA = "1.333223684"
ROOT_TEMPERATURE_K = "300"
ROOT_PRESSURE_VARIABLE = {
    "type": "INSFVPressureVariable",
    "initial_condition": ROOT_PRESSURE_PA,
    "block": "plasma",
}
ROOT_OUTLET_PRESSURE_BC = {
    "type": "INSFVOutletPressureBC",
    "variable": "p",
    "boundary": "outlet",
    "function": ROOT_PRESSURE_PA,
}


def canonicalize_s6_root_gas_state(
    layered: dict[str, str], base_name: str
) -> tuple[dict[str, str], dict]:
    """Use root pressure as pressure FV IC, then pressure FV Functor at runtime.

    The original .i input is immutable; every mutation is scratch-only.
    No independent p/p_fixed/T_g_fixed coefficient producers survive.
    """
    base = layered[base_name]
    pressure_blocks = [
        m for m in BLOCK.finditer(base)
        if m.group("name") == "p" and
        re.findall(r"(?m)^\[([A-Za-z0-9_]+)\]\s*$",
                   base[:m.start()])[-1:] == ["Variables"]
    ]
    if (len(pressure_blocks) != 1 or
        parameters(pressure_blocks[0].group("body")) != ROOT_PRESSURE_VARIABLE):
        raise ValueError("HYBRID_ROOT_PRESSURE_VARIABLE_IC_IDENTITY_CHANGED")

    outlet_blocks = [
        m for m in BLOCK.finditer(base)
        if m.group("name") == "neutral_outlet_p" and
        re.findall(r"(?m)^\[([A-Za-z0-9_]+)\]\s*$",
                   base[:m.start()])[-1:] == ["FVBCs"]
    ]
    if (len(outlet_blocks) != 1 or
        parameters(outlet_blocks[0].group("body")) != ROOT_OUTLET_PRESSURE_BC):
        raise ValueError("HYBRID_ROOT_PRESSURE_OUTLET_BC_IDENTITY_CHANGED")

    constant_blocks = [
        m for m in BLOCK.finditer(base)
        if m.group("name") == "constants" and
        re.findall(r"(?m)^\[([A-Za-z0-9_]+)\]\s*$",
                   base[:m.start()])[-1:] == ["FunctorMaterials"]
    ]
    if len(constant_blocks) != 1:
        raise ValueError("HYBRID_ROOT_GAS_CONSTANT_OWNER_COUNT_CHANGED")
    original = parameters(constant_blocks[0].group("body"))
    expected = {
        **ARCHIVED_COEFFICIENT_CONSTANTS,
        "prop_names": ("'p_fixed T_g_fixed O2p_mobility O2p_diffusivity "
                       "Om_mobility Om_diffusivity Op_mobility Op_diffusivity "
                       "carrier_one'"),
    }
    if original != expected:
        raise ValueError("HYBRID_ROOT_GAS_CONSTANT_IDENTITY_CHANGED")

    # Remove the two old state providers, retaining all original ion and
    # carrier numbers in the identical order and with identical precision.
    constants = constant_blocks[0]
    ctext = constants.group(0)
    ctext = ctext.replace("p_fixed T_g_fixed ", "", 1)
    ctext = ctext.replace(
        "1.333223684 300 10 0.25851999786435537",
        "10 0.25851999786435537", 1)
    if ctext == constants.group(0):
        raise ValueError("HYBRID_ROOT_GAS_CONSTANT_REWRITE_FAILED")

    # The native outlet pressure must follow the SAME root input parameter
    # (not another editable 1.333223684). MOOSE's standard brace replacement
    # reads the root parameter without creating another source or Functor.
    outlet = outlet_blocks[0]
    otext = outlet.group(0).replace(
        "    function = " + ROOT_PRESSURE_PA,
        "    function = ${Physics/Plasmas/pressure}", 1)
    if otext == outlet.group(0):
        raise ValueError("HYBRID_ROOT_OUTLET_COUPLING_REWRITE_FAILED")

    # Source order matters. All offsets refer to the original staged base.
    pressure = pressure_blocks[0]
    ptext = pressure.group(0).replace(
        "    initial_condition = " + ROOT_PRESSURE_PA + "\n", "", 1)
    if ptext == pressure.group(0):
        raise ValueError("HYBRID_ROOT_PRESSURE_INITIAL_CONDITION_RETIRE_FAILED")
    for match, replacement in sorted(
        ((constants, ctext), (outlet, otext), (pressure, ptext)),
        key=lambda pair: pair[0].start(),
        reverse=True
    ):
        base = base[:match.start()] + replacement + base[match.end():]

    migrated = dict(layered)
    migrated[base_name] = base
    touched = []
    counts = {"p": 0, "T_g_fixed": 0}
    for filename, source in migrated.items():
        before = source
        for old, new in (("p", "pressure"), ("T_g_fixed", "temperature")):
            source, count = re.subn(
                r"(?<![A-Za-z0-9_])" + re.escape(old) +
                r"(?![A-Za-z0-9_])", new, source)
            counts[old] += count
        for token in ("p", "p_fixed", "T_g_fixed"):
            if re.search(r"(?<![A-Za-z0-9_])" + re.escape(token) +
                         r"(?![A-Za-z0-9_])", source):
                raise ValueError("HYBRID_ROOT_GAS_LEGACY_OWNER_REMAINS_" + token)
        migrated[filename] = source
        if source != layered[filename]:
            touched.append(filename)
    if counts["p"] < 15 or counts["T_g_fixed"] < 5:
        raise ValueError("HYBRID_ROOT_GAS_CONSUMER_COVERAGE_INCOMPLETE")

    expected_names = (
        "'O2p_mobility O2p_diffusivity Om_mobility Om_diffusivity "
        "Op_mobility Op_diffusivity carrier_one'")
    expected_values = (
        "'10 0.25851999786435537 10 0.25851999786435537 "
        "10 0.25851999786435537 1.0'")
    new_constants = [
        m for m in BLOCK.finditer(migrated[base_name])
        if m.group("name") == "constants"
    ]
    if (len(new_constants) != 1 or
        parameters(new_constants[0].group("body")) != {
            **ARCHIVED_COEFFICIENT_CONSTANTS,
            "prop_names": expected_names,
            "prop_values": expected_values,
        }):
        raise ValueError("HYBRID_ROOT_GAS_ION_TRANSPORT_VALUES_CHANGED")
    if "[pressure]\n    type = INSFVPressureVariable" not in migrated[base_name]:
        raise ValueError("HYBRID_ROOT_PRESSURE_SOLVER_VARIABLE_MISSING")
    if "    initial_condition = 1.333223684" in migrated[base_name]:
        raise ValueError("HYBRID_DUPLICATE_PRESSURE_INITIAL_CONDITION")
    if "function = ${Physics/Plasmas/pressure}" not in migrated[base_name]:
        raise ValueError("HYBRID_ROOT_OUTLET_SOURCE_MISSING")

    return migrated, {
        "status": "NATIVE_PRESSURE_SOLVED_ROOT_PRESSURE_INITIAL_CONDITION",
        "pressure_initial_pa": float(ROOT_PRESSURE_PA),
        "temperature_constant_k": float(ROOT_TEMPERATURE_K),
        "pressure_solver_variable": "pressure",
        "pressure_runtime_functor": "pressure",
        "temperature_runtime_functor": "temperature",
        "external_pressure_functor_created": False,
        "native_pressure_initial_retired": True,
        "native_p_fixed_temperature_fixed_retired": True,
        "root_outlet_parameter_coupled": True,
        "changed_staged_native_layers": sorted(touched),
        "substitution_counts": counts,
        "original_pressure_block_sha256":
            digest(pressure.group(0).encode("utf-8")),
        "original_outlet_block_sha256":
            digest(outlet.group(0).encode("utf-8")),
    }




def prepare(staged_chem_dir: Path, ordered: list[str], case: str) -> dict:
    if case not in ("417", "941"):
        raise ValueError("HYBRID_CASE_NOT_417_OR_941")
    staged_chem_dir = Path(staged_chem_dir).resolve()
    if len(ordered) != 11 or Path(ordered[-1]).name != "migrated_continuity.i":
        raise ValueError("HYBRID_REQUIRES_EXACT_11_STAGED_LAYERS")
    names = [Path(name).name for name in ordered]
    if len(set(names)) != 11 or not all((staged_chem_dir / n).is_file() for n in names):
        raise ValueError("HYBRID_MISSING_OR_DUPLICATE_STAGED_INPUT")
    first = staged_chem_dir / names[0]
    overlay = staged_chem_dir / names[-1]
    source = first.read_text(encoding="utf-8")
    original_sha = digest(source.encode("utf-8"))
    removed = []

    density = {}
    for var in VAR_NAMES:
        # Compare against original full-precision .i lexical bytes, not
        # str(float) which shortens e.g. -18.829829186913098 to -18.8298291869131.
        expected = {"initial_condition": PINNED_INITIAL_LOG[var], "block": "plasma"}
        if var in ("log_e", "log_e_energy"):
            expected.update(family="LAGRANGE", order="FIRST")
        else:
            expected["type"] = "MooseVariableFVReal"
        source, receipt = retire(source, "Variables", var, expected)
        removed.append(receipt)
        if var != "log_e_energy":
            density[var[4:]] = math.exp(float(PINNED_INITIAL_LOG[var])) * N_A

    for name, expected in SOURCE_KERNEL.items():
        source, receipt = retire(source, "Kernels", name, expected)
        removed.append(receipt)
    for name, expected in SOURCE_MATERIAL.items():
        source, receipt = retire(source, "FunctorMaterials", name, expected)
        removed.append(receipt)

    source, sheath_bc_rebinds = migrate_exact_s6_fem_sheath(source)

    # All non-electron Native owners remain unchanged. Electron wall-flux
    # material is now exclusively auto-created by DriftDiffusion.
    for signature in ("[potential]", "[phi_diffusion]", "[phi_source]",
                      "[sigma_surface_current]", "[ion_molar_density]",
                      "[ni_time]"):
        if signature not in source:
            raise ValueError("HYBRID_UNCOVERED_NATIVE_OWNER_LOST: " + signature)
    if any(re.search(r"(?m)^  \[" + re.escape(name) + r"\]\s*$", source)
           for name in VAR_NAMES):
        raise ValueError("HYBRID_DUPLICATE_GENERATED_STATE_REMAINS")
    if len(removed) != 12:
        raise ValueError("HYBRID_EXPECTED_EXACTLY_TWELVE_RETIRED_OWNERS")

    common = json.loads((staged_chem_dir / "chemistry/oxygen_s6_common.json").read_text())
    variant = json.loads(
        (staged_chem_dir / f"chemistry/oxygen_s6_{case}.json").read_text())
    if set(common["species"]) != {"e","O2","O","O2p","Om","Op","O2a"}:
        raise ValueError("HYBRID_COMMON_SPECIES_IDENTITY_CHANGED")
    if variant.get("species"):
        raise ValueError("HYBRID_VARIANT_SPECIES_OVERLAY_NOT_EMPTY")
    for id in density:
        if not math.isfinite(density[id]) or density[id] <= 0:
            raise ValueError("HYBRID_INITIAL_DENSITY_INVALID_" + id)

    # Preserve the existing public 400-W mean-energy lookup source EXACTLY.
    # The JSON resides next to the old .i, so its relative table path is
    # identical to the removed Native DDTransportMaterial's table_file.
    table_rel = "../Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
    table_path = (staged_chem_dir / table_rel).resolve()
    if not table_path.is_file() or not table_path.stat().st_size:
        raise ValueError("HYBRID_ORIGINAL_ELECTRON_TRANSPORT_TABLE_NOT_STAGED")
    species = {}
    for id in ("e", "O2p", "Om", "Op"):
        original = common["species"][id]
        entry = {
            "elements": original["elements"],
            "charge_number": original["charge_number"],
            "initial_number_density": density[id],
        }
        if id == "e":
            entry.update({
                "transport_coef": "lookup",
                "table_file": table_rel,
                "table_units": "reduced",
                "pressure": "pressure",
                "gas_temperature": "temperature",
                "bounds_policy": "clamp",
                "energy_transport_coef": "fluid",
            })
        else:
            entry.update({
                "transport_coef": "functor",
                "mobility": id + "_mobility",
                "diffusivity": id + "_diffusivity",
            })
        species[id] = entry
    # The integrated mechanism carries ALL seven species (neutrals too),
    # all seven common and one variant reaction, and all four transport
    # records. Construct the expected document from the pinned original
    # public mechanisms and compare against the reviewed in-repo JSON.
    if set(variant["equations"]) != {f"EI-{case}"} or (
        len(variant["reactions"]) != 1 or
        variant["reactions"][0]["id"] != f"EI-{case}"
    ):
        raise ValueError("HYBRID_INTEGRATED_VARIANT_REACTION_IDENTITY_CHANGED")
    if (set(common["equations"]) & set(variant["equations"])) or any(
        r["id"] in {x["id"] for x in common["reactions"]}
        for r in variant["reactions"]
    ):
        raise ValueError("HYBRID_INTEGRATED_REACTION_COLLISION")
    all_species = {key: dict(value) for key, value in common["species"].items()}
    for id, value in species.items():
        all_species[id].update(value)
    # Only species transport/chemistry data and the eight electron FEM sheath
    # BCs are migrated. FV ion, Poisson and Navier-Stokes BCs remain Native.
    masses = {"O2": 0.032, "O": 0.016, "O2p": 0.032,
              "Om": 0.016, "Op": 0.016, "O2a": 0.032}
    for id, mass in masses.items():
        all_species[id]["molar_mass_kg_mol"] = mass
    for id, live in {"O2": "w_O2_constraint", "O": "w_O",
                     "O2a": "w_O2s"}.items():
        all_species[id]["mass_fraction_functor"] = live

    kinetic_tables = {
        "EI-02": "o2_elastic.txt",
        "EI-17": "o_elastic.txt",
        "EI-415": "private_rates/EI-415_O2_X.txt",
        "EI-401": "private_rates/EI-401_O2_X.txt",
        "EI-407": "private_rates/EI-407_O2_X.txt",
        "EI-2069": "private_rates/EI-2069_O2_a1Delta.txt",
        "EI-417": "private_rates/EI-417_O2_X.txt",
        "EI-941": "private_rates/EI-941_O_3P.txt",
    }
    merged_reactions = [dict(r) for r in
                        [*common["reactions"], *variant["reactions"]]]
    for reaction in merged_reactions:
        reaction.pop("provenance", None)  # archived source retains provenance
        if reaction["id"] in kinetic_tables:
            reaction["table"] = kinetic_tables[reaction["id"]]
        elif reaction["id"] == "H25":
            reaction["rate"] = {
                "model": "power_law", "A": 1.204428152e7,
                "basis": "molar", "T_ref": 300, "exponent": 0.4
            }
        else:
            raise ValueError("HYBRID_UNKNOWN_REACTION_RATE_OWNER")
        if reaction["id"] in ("EI-02", "EI-17"):
            reaction["energy_loss_eV"] = {"model": "elastic"}

    boundaries = {}
    for bc_name, (type_name, sideset) in SHEATH_BC_SPEC.items():
        side = sideset.strip("'")
        bc = {
            "type": type_name,
            "variable": "log_e" if type_name == "FEMElectronSheathBC" else "log_e_energy",
            "wall_number_flux": "e_wall_number_flux",
        }
        if type_name == "FEMElectronEnergySheathBC":
            bc["mean_energy"] = "e_energy_eV"
        boundaries.setdefault(side, {"bcs": {}})["bcs"][bc_name] = bc

    expected_json = {
        "species": all_species,
        "equations": {**common["equations"], **variant["equations"]},
        "reactions": merged_reactions,
        "boundaries": boundaries,
    }
    if (len(expected_json["species"]) != 7 or
        len(expected_json["reactions"]) != 8 or
        len(expected_json["equations"]) != 8 or
        {r["id"] for r in expected_json["reactions"]} !=
            set(expected_json["equations"])):
        raise ValueError("HYBRID_INTEGRATED_MECHANISM_COMPLETENESS_ERROR")
    unified_name = f"unified_s6_{case}.json"
    unified_source = ROOT / "chemistry" / unified_name
    unified_raw = unified_source.read_bytes()
    integrated_json = json.loads(unified_raw)
    if integrated_json != expected_json:
        raise ValueError("HYBRID_INTEGRATED_JSON_DIFFERS_FROM_PINNED_MECHANISM")
    if any(
        integrated_json["species"][id].get("mobility") != f"{id}_mobility" or
        integrated_json["species"][id].get("diffusivity") != f"{id}_diffusivity"
        for id in ("O2p", "Om", "Op")
    ):
        raise ValueError("HYBRID_INTEGRATED_ION_SOURCE_CONTRACT_MISMATCH")

    template = overlay.read_text(encoding="utf-8")
    old_files = (
        f"files = 'chemistry/oxygen_s6_common.json "
        f"chemistry/oxygen_s6_{case}.json'"
    )
    if template.count(old_files) != 1:
        raise ValueError("HYBRID_S6_MECHANISM_FILES_NOT_PINNED")
    template = template.replace(
        old_files,
        f"files = '{unified_name}'\n"
        f"    pressure = {ROOT_PRESSURE_PA}\n"
        f"    temperature = {ROOT_TEMPERATURE_K}\n"
        "    state_model = ideal_gas", 1)
    energy_section = (
        "        [Energy]\n"
        "          block = plasma\n"
        "          fem_species = 'e'\n"
        "        []"
    )
    if template.count(energy_section) != 1:
        raise ValueError("HYBRID_ENERGY_ACTION_NOT_EXACT_LEGACY_PARTIAL")
    template = template.replace(
        energy_section,
        "        [Energy]\n"
        "          block = plasma\n"
        "          fem_species = 'e'\n"
        "          fem_potential = potential\n"
        "          initial_molar_energy_density_eV = "
        + repr(math.exp(float(PINNED_INITIAL_LOG["log_e_energy"]))) + "\n"
        "        []", 1)
    if "[BCs]" in template or "[Kernels]" in template or "[FunctorMaterials]" in template:
        raise ValueError("HYBRID_OVERLAY_MUST_NOT_DUPLICATE_NATIVE_OWNERS")
    if "fem_potential = potential" not in template or (
        template.count("fem_potential = potential") != 2):
        raise ValueError("HYBRID_FULL_FEM_CONTINUITY_AND_ENERGY_NOT_ENABLED")

    # All changes are isolated to the scratch input. The original Native
    # coefficient material is the SOLE owner; all legacy consumers are
    # rebound to the same numbers under species-prefixed identifiers.
    native_inputs = {
        n: (source if n == first.name else
            (staged_chem_dir / n).read_text(encoding="utf-8"))
        for n in names[:-1]
    }
    native_inputs, ion_rename_receipt = canonicalize_native_ion_transport_sources(
        native_inputs, first.name
    )
    native_inputs, gas_state_receipt = canonicalize_s6_root_gas_state(
        native_inputs, first.name
    )
    native_inputs, kinetic_receipt = retire_staged_kinetic_owners(
        native_inputs, integrated_json
    )
    before = {n: digest((staged_chem_dir / n).read_bytes()) for n in names}
    # Validate all inputs and source identities before any scratch write.
    json_path = staged_chem_dir / unified_name
    if json_path.exists():
        raise ValueError("HYBRID_INTEGRATED_JSON_OUTPUT_ALREADY_EXISTS")
    for n, revised in native_inputs.items():
        if digest(revised.encode("utf-8")) != before[n]:
            (staged_chem_dir / n).write_text(revised, encoding="utf-8")
    overlay.write_text(template, encoding="utf-8")
    json_path.write_bytes(unified_raw)
    after = {n: digest((staged_chem_dir / n).read_bytes()) for n in names}
    changed = [n for n in names if before[n] != after[n]]
    expected_changed = set(ion_rename_receipt["changed_staged_native_layers"])
    expected_changed.update(gas_state_receipt["changed_staged_native_layers"])
    expected_changed.update(
        n for n, value in native_inputs.items()
        if digest(value.encode("utf-8")) != before[n]
    )
    expected_changed.update((first.name, overlay.name))
    if set(changed) != expected_changed:
        raise ValueError("HYBRID_UNEXPECTED_NATIVE_LAYER_EDIT: " + repr(changed))
    return {
        "schema": "issue402_s6_hybrid_json_native_owner_migration_v1",
        "case": case,
        "status": "SCRATCH_HYBRID_PREPARED_NO_SOLVE",
        "native_owner_preservation":
            "NATIVE_EQUATIONS_UNCHANGED_WITH_ROOT_PRESSURE_IC_AND_SPECIES_FUNCTORS",
        "native_species_coefficient_binding_migration": ion_rename_receipt,
        "native_kinetic_rate_cutover": kinetic_receipt,
        "root_gas_state_pressure_initial_condition": gas_state_receipt,
        "integrated_mechanism_json": unified_name,
        "integrated_reaction_count": len(integrated_json["reactions"]),
        "integrated_species_count": len(integrated_json["species"]),
        "removed_generated_owner_count": len(removed),
        "removed_owners": removed,
        "rebound_native_sheath_bcs": sheath_bc_rebinds,
        "rebound_native_sheath_bc_count": len(sheath_bc_rebinds),
        "changed_staged_layers": changed,
        "initial_number_densities_per_m3": density,
        "initial_molar_energy_density_eV": math.exp(float(PINNED_INITIAL_LOG["log_e_energy"])),
        "electron_transport_table_sha256": digest(table_path.read_bytes()),
        "hybrid_json_sha256": digest(json_path.read_bytes()),
        "integrated_json_source_sha256": digest(unified_raw),
        "original_canonical_s6_base_sha256": original_sha,
        "overlay_sha256": digest(overlay.read_bytes()),
        "science_acceptance": "HOLD",
    }
