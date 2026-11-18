#!/usr/bin/env python3
"""Public-data-only S6-417/941 native P2: original B versus option-first D.

Do not execute a solver time step. Never access archived private reference rates.
The C legacy migration is only an immutable source of the 10-layer no-ne_transport
base: its old migrated_continuity.i is replaced by an independently pinned overlay.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
P2_PATH = ROOT / "experiments/Issue493_s6_boltzmann/public_p2_check.py"
SPEC = importlib.util.spec_from_file_location("issue493_public_p2", P2_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Cannot load pinned public P2 preflight")
p2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p2)

HISTORICAL_SHA = "29d1acc6ef7969908b86719e4b95c73a1565136d"
OCI = ("ghcr.io/hyungseonsong-plasma/physics-build-base@"
       "sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008")
OVERLAY = """# Review-only new option DSL overlay; NOT pinned P3 C input.
# Pair ONLY with the C candidate base (which removes the original ne_transport).
# No Material/Functor name is modified.
[Physics]
  [Plasmas]
    files = plasma_species_only.json
    [Transport]
      [DriftDiffusion]
        [Continuity]
          block = plasma
          fem_species = 'e'
          fvm_species = 'O2p Om Op'
          fem_potential = potential
        []
      []
    []
  []
[]
[FunctorMaterials]
  [O2p_species_transport_alias]
    type = DDTransportMaterial
    model = functor
    species_id = O2p
    mobility_source = ion_mobility
    diffusivity_source = ion_diffusion
  []
  [Om_species_transport_alias]
    type = DDTransportMaterial
    model = functor
    species_id = Om
    mobility_source = negative_ion_mobility
    diffusivity_source = negative_ion_diffusion
  []
  [Op_species_transport_alias]
    type = DDTransportMaterial
    model = functor
    species_id = Op
    mobility_source = atomic_positive_ion_mobility
    diffusivity_source = atomic_positive_ion_diffusion
  []
[]
"""
OVERLAY_SHA256 = "edf3f8e8194927e93783d136066799d60df2673af9245d6d4b990fb7d267b513"
CASES = ("417", "941")
VARIANTS = ("B", "D")


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def validate_overlay() -> None:
    if hashlib.sha256(OVERLAY.encode("utf-8")).hexdigest() != OVERLAY_SHA256:
        raise ValueError("Option-only review overlay SHA changed")
    for forbidden in ("variables =", "fem_kernel_names", "fem_mobility =",
                      "fem_diffusion =", "mobility =", "diffusivity =", "[ne_transport]"):
        if forbidden in OVERLAY:
            raise ValueError(f"Unexpected option/provider migration: {forbidden}")
    expected = {
        "fem_species": "'e'", "fvm_species": "'O2p Om Op'",
        "files": "plasma_species_only.json",
        "fem_potential": "potential",
    }
    for k, v in expected.items():
        if not re.search(r"(?m)^\s*" + k + r"\s*=\s*" + re.escape(v) + r"\s*$", OVERLAY):
            raise ValueError(f"Missing/modified binding: {k}")


# Compatibility belongs in an isolated *test-data migration*, not a runtime
# Physics option. B is byte-identical; only staged D inputs are canonicalized.
CANONICAL_STATE_NAMES = {
    "log_ne": "log_e",
    "log_ni": "log_O2p",
    "log_nm": "log_Om",
    "log_nop": "log_Op",
}
_STATE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:" + "|".join(map(re.escape, CANONICAL_STATE_NAMES)) +
    r")(?![A-Za-z0-9_])"
)


def canonicalize_staged_D_inputs(chemistry: Path, ordered: list[str]) -> dict:
    """Modify only disposable D copies, never immutable B/C or source archives.

    In the same bounded migration as ne_transport -> generated e_transport,
    remove the one original ne_time; ContinuityEq now generates e_time with
    the identical PhysicsFEMLogMolarTimeDerivative equation and block.
    """
    if len(ordered) != 11 or Path(ordered[-1]).name != "migrated_continuity.i":
        raise ValueError("Unexpected staged D input layer order")

    time_pattern = re.compile(
        r"(?m)^  \[ne_time\][ \t]*\r?\n"
        r"(?P<body>(?:^    [^\r\n]*\r?\n)+)"
        r"^  \[\][ \t]*(?:\r?\n|$)"
    )
    expected_time = {
        "type": "PhysicsFEMLogMolarTimeDerivative",
        "variable": "log_ne",
        "block": "plasma",
    }
    first_layer = Path(ordered[0]).name
    changes: dict[str, dict] = {}
    pending: list[tuple[Path, str]] = []
    removed_time: list[dict] = []
    total = 0
    for relative in ordered[:-1]:
        name = Path(relative).name
        if name != relative.split("/")[-1] or not name.endswith(".i"):
            raise ValueError("Unsafe staged D layer name")
        path = chemistry / name
        before = path.read_bytes()
        source = before.decode("utf-8")

        # The native-to-DSL substitution is exactly one known operator,
        # declared in the original base layer, with no extra parameters.
        matches = list(time_pattern.finditer(source))
        if len(matches) > 1 or ("[ne_time]" in source and not matches):
            raise ValueError("Ambiguous or malformed original ne_time block")
        if matches:
            if name != first_layer:
                raise ValueError("Original ne_time owner must reside in the first layer")
            match = matches[0]
            pairs = re.findall(
                r"(?m)^    ([a-z_]+)[ \t]*=[ \t]*([^\r\n]+)$",
                match.group("body"),
            )
            if len(pairs) != 3 or {key: value.strip() for key, value in pairs} != expected_time:
                raise ValueError("Original ne_time parameters differ from pinned Native S6")
            removed_time.append({
                "source_layer": name,
                "old_name": "ne_time",
                "generated_name": "e_time",
                "kernel_type": expected_time["type"],
                "original_block_sha256": hashlib.sha256(
                    match.group(0).encode("utf-8")).hexdigest(),
            })
            source = source[:match.start()] + source[match.end():]

        # D's C-derived base must have removed ne_transport already.
        if re.search(r"(?m)^[ \t]*\[ne_transport\][ \t]*$", source):
            raise ValueError("Staged D input still contains the original ne_transport")

        observed = {old: len(re.findall(
            r"(?<![A-Za-z0-9_])" + re.escape(old) + r"(?![A-Za-z0-9_])", source))
            for old in CANONICAL_STATE_NAMES}
        converted = _STATE_TOKEN.sub(
            lambda match: CANONICAL_STATE_NAMES[match.group()], source)
        if _STATE_TOKEN.search(converted) or "[ne_time]" in converted:
            raise ValueError("Staged D retains a legacy state or time owner")

        total += sum(observed.values())
        pending.append((path, converted))
        changes[name] = {
            "original_sha256": hashlib.sha256(before).hexdigest(),
            "staged_sha256": hashlib.sha256(converted.encode("utf-8")).hexdigest(),
            "state_name_substitutions": {k: v for k, v in observed.items() if v},
        }

    # Fail before writing any copy if ownership or source identity is unclear.
    if len(removed_time) != 1:
        raise ValueError("Expected exactly one original ne_time in staged S6 D")
    if total == 0:
        raise ValueError("No archived S6 solver states found in staged D input")
    for path, converted in pending:
        if path.read_text(encoding="utf-8") != converted:
            path.write_text(converted, encoding="utf-8")
    return {
        "status": "SCRATCH_ONLY_CANONICAL_STATE_AND_TIME_OWNER_REWRITE",
        "changed_reference_count": total,
        "removed_native_time": removed_time[0],
        "files": changes,
    }



# Historical archived decks retain old factory names only as provenance.
# No old Material object aliases are registered in the application.
# Rename the explicit type fields in disposable B/D scratch copies. No factory
# aliases are installed by the application and no archived input is rewritten.
RENAMED_FEM_KERNEL_TYPES = {
    "PhysicsFEMLogMolarTimeDerivative": "FEMLogMolarTimeDerivative",
    "PhysicsFEMLogMolarDriftDiffusion": "FEMLogMolarDriftDiffusion",
    "PhysicsFEMLogMolarElectronJouleHeating": "FEMLogMolarElectronJouleHeating",
    # Wave2-6-B: exact historical lower-D observers retain their measurements.
    # Migrate type tokens only, never install legacy factory aliases.
    "PhysicsLowerDSurfaceCurrentProbeAux": "LowerDSurfaceCurrentProbeAux",
    "PhysicsWaferD1GeometryProbeAux": "WaferD1GeometryProbeAux",
    # Archived S6 inputs are rewritten only after their pinned byte hashes are checked.
    "PhysicsThermalDiffusionMaterial": "NVTransportMaterial",
    "DDMaterial": "DDTransportMaterial",
    "NVMaterial": "NVTransportMaterial",
    "ElectronImpactRateMaterial": "EIRateCoefMaterial",
    "PhysicsElectronImpactRateMaterial": "EIRateCoefMaterial",
}
_FEM_TYPE_LINE = re.compile(
    r"(?m)^(?P<indent>[ \t]*type[ \t]*=[ \t]*)(?P<name>"
    + "|".join(map(re.escape, RENAMED_FEM_KERNEL_TYPES))
    + r")(?P<end>[ \t]*\r?$)"
)



def reconcile_staged_D_json_initials(chemistry: Path, ordered: list[str]) -> dict:
    """Pin the four D log-state initials to the archived Native S6, scratch only.

    The JSON-owned DD Physics generates exactly these four solver variables/ICs;
    delete the competing old native declarations without touching log_energy,
    physics equations, original source inputs or the reviewed public overlay.
    """
    if (len(ordered) != 11 or Path(ordered[-1]).name != "migrated_continuity.i"
            or len({Path(item).name for item in ordered}) != 11
            or any(Path(item).name != item.split("/")[-1] or
                   not item.endswith(".i") for item in ordered)):
        raise ValueError("S6_D_INITIAL_UNEXPECTED_LAYER_SET")
    spec = importlib.util.spec_from_file_location(
        "issue402_s6_initial_contract",
        ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry/prepare_hybrid_json_s6.py")
    if spec is None or spec.loader is None:
        raise ValueError("S6_D_INITIAL_PINNED_DONOR_MISSING")
    donor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(donor)
    states = {"e": "log_e", "O2p": "log_O2p", "Om": "log_Om", "Op": "log_Op"}
    first = chemistry / Path(ordered[0]).name
    original = first.read_text(encoding="utf-8")
    if "[log_energy]\n" not in original:
        raise ValueError("S6_D_INITIAL_NATIVE_ENERGY_OWNER_MISSING")
    remaining, retired, densities = original, [], {}
    for species, variable in states.items():
        lexical = donor.PINNED_INITIAL_LOG[variable]
        expected = {"initial_condition": lexical, "block": "plasma"}
        if species == "e":
            expected.update(family="LAGRANGE", order="FIRST")
        else:
            expected["type"] = "MooseVariableFVReal"
        remaining, receipt = donor.retire(remaining, "Variables", variable, expected)
        retired.append(receipt)
        density = math.exp(float(lexical)) * donor.N_A
        if not math.isfinite(density) or density <= 0:
            raise ValueError("S6_D_INITIAL_PHYSICAL_DENSITY_INVALID")
        densities[species] = density
    for relative in ordered[1:-1]:
        source = (chemistry / Path(relative).name).read_text(encoding="utf-8")
        for variable in states.values():
            if re.search(r"(?m)^  \[" + re.escape(variable) + r"\]\s*$", source):
                raise ValueError("S6_D_INITIAL_SECONDARY_NATIVE_OWNER_" + variable)

    source_path = ROOT / "experiments/Issue402_plasma_dsl_g1/plasma_species_only.json"
    staged_path = chemistry / "plasma_species_only.json"
    original_json = source_path.read_bytes()
    if staged_path.read_bytes() != original_json:
        raise ValueError("S6_D_INITIAL_SPECIES_JSON_SOURCE_DRIFT")
    payload = json.loads(original_json)
    if (set(payload) != {"species", "equations", "reactions"}
            or payload["equations"] != {} or payload["reactions"] != []
            or set(payload["species"]) != {"e", "O2", "O", "O2p", "Om", "Op"}):
        raise ValueError("S6_D_INITIAL_SPECIES_ONLY_SCHEMA_MISMATCH")
    for species, charge in {"e": -1, "O2p": 1, "Om": -1, "Op": 1}.items():
        record = payload["species"][species]
        if set(record) != {"elements", "charge_number"} or record["charge_number"] != charge:
            raise ValueError("S6_D_INITIAL_CHARGE_OR_OWNER_" + species)
        record["initial_number_density"] = densities[species]
    new_json = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    # All identity, ownership and schema preflights finish before either write.
    first.write_text(remaining, encoding="utf-8")
    staged_path.write_bytes(new_json)
    return {
        "status": "SCRATCH_ONLY_JSON_INITIALS_FOUR_NATIVE_OWNERS_RETIRED",
        "retired_native_variables": sorted(states.values()),
        "densities_m3": densities,
        "native_before_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "native_after_sha256": hashlib.sha256(remaining.encode()).hexdigest(),
        "json_original_sha256": hashlib.sha256(original_json).hexdigest(),
        "json_staged_sha256": hashlib.sha256(new_json).hexdigest(),
        "P3": "NOT_RUN", "science": "SCIENCE_HOLD",
    }




def cutover_staged_D_transport_owners(chemistry: Path, ordered: list[str]) -> dict:
    """Move exactly four historical DD coefficient owners to Physics/JSON.

    This is a D-only disposable input edit, after exact old lookup/material
    registration remapping.  B and the reviewed OVERLAY bytes stay immutable.
    Reuse all original coefficient Functors and the 400-W reduced lookup table;
    never invent a new mobility/diffusivity or an energy closure.
    """
    if (len(ordered) != 11 or Path(ordered[-1]).name != 'migrated_continuity.i'
            or len({Path(item).name for item in ordered}) != 11):
        raise ValueError('P6_D1_UNEXPECTED_STAGED_11_LAYERS')
    if any(Path(item).name != item.split('/')[-1] or
           not Path(item).name.endswith('.i') for item in ordered):
        raise ValueError('P6_D1_UNSAFE_STAGED_PATH')
    first = chemistry / Path(ordered[0]).name
    overlay = chemistry / 'migrated_continuity.i'
    staged_json = chemistry / 'plasma_species_only.json'
    if (not all((chemistry / Path(item).name).is_file() for item in ordered)
            or not staged_json.is_file() or
            first.is_symlink() or overlay.is_symlink() or staged_json.is_symlink()):
        raise ValueError('P6_D1_MISSING_OR_SYMLINK_INPUT')
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'p6_d1_exact_historical_material',
        ROOT / 'experiments/Issue402_plasma_dsl_g1/chemistry/prepare_hybrid_json_s6.py')
    if spec is None or spec.loader is None:
        raise ValueError('P6_D1_HISTORICAL_MATERIAL_CONTRACT_MISSING')
    donor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(donor)
    first_before = first.read_bytes()
    overlay_before = overlay.read_bytes()
    json_before = staged_json.read_bytes()
    first_after, electron = donor.retire(
        first_before.decode('utf-8'), 'FunctorMaterials',
        'electron_transport', donor.SOURCE_MATERIAL['electron_transport'])
    aliases = {
        'O2p': ('ion_mobility', 'ion_diffusion'),
        'Om': ('negative_ion_mobility', 'negative_ion_diffusion'),
        'Op': ('atomic_positive_ion_mobility', 'atomic_positive_ion_diffusion'),
    }
    overlay_after = overlay_before.decode('utf-8')
    removed = [electron]
    for species, (mobility, diffusivity) in aliases.items():
        overlay_after, item = donor.retire(
            overlay_after, 'FunctorMaterials',
            species + '_species_transport_alias',
            {'type': 'DDTransportMaterial', 'model': 'functor',
             'species_id': species, 'mobility_source': mobility,
             'diffusivity_source': diffusivity})
        removed.append(item)
    if len(removed) != 4:
        raise ValueError('P6_D1_EXPECT_EXACT_4_MATERIALS')
    payload = json.loads(json_before)
    species_records = payload.get('species', {})
    if set(payload) != {'species', 'equations', 'reactions'} or (
            set(species_records) != {'e', 'O2', 'O', 'O2p', 'Om', 'Op'} or
            payload['equations'] != {} or payload['reactions'] != []):
        raise ValueError('P6_D1_OPTION_ONLY_JSON_IDENTITY_DRIFT')
    for species, charge in {'e': -1, 'O2p': 1, 'Om': -1, 'Op': 1}.items():
        record = species_records[species]
        if (set(record) != {'elements', 'charge_number', 'initial_number_density'}
                or record['charge_number'] != charge or
                not isinstance(record['initial_number_density'], (int, float)) or
                not math.isfinite(record['initial_number_density']) or
                record['initial_number_density'] <= 0):
            raise ValueError('P6_D1_PRECUTOVER_INITIAL_IDENTITY_' + species)
    # Same table, pressure, temperature and clamp policy as the retired
    # electron_transport source; legacy flat JSON schema is explicitly
    # supported for this historical option-only path.
    table_rel = '../Issue91_real_qvt_r3/r3_e0/electron_moments.txt'
    table_path = (chemistry / table_rel).resolve()
    if (not table_path.is_file() or table_path.is_symlink() or
            hashlib.sha256(table_path.read_bytes()).hexdigest() !=
            '35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b'):
        raise ValueError('P6_D1_HISTORICAL_ELECTRON_TABLE_SHA_MISMATCH')
    species_records['e'].update({
        'transport_coef': 'lookup', 'table_file': table_rel,
        'table_units': 'reduced', 'pressure': 'p',
        'gas_temperature': 'T_g_fixed', 'bounds_policy': 'clamp',
        'energy_transport_coef': 'fluid',
    })
    for species, (mobility, diffusivity) in aliases.items():
        species_records[species].update({
            'transport_coef': 'functor', 'mobility': mobility,
            'diffusivity': diffusivity,
        })
    json_after = (json.dumps(payload, indent=2, sort_keys=True) + '\n').encode()
    # No persistent writes until every source, type, schema, table and owner
    # check above has succeeded. All paths are disposable scratch, not originals.
    first.write_text(first_after, encoding='utf-8')
    overlay.write_text(overlay_after, encoding='utf-8')
    staged_json.write_bytes(json_after)
    for path, expected in ((first, first_after.encode()),
                           (overlay, overlay_after.encode()),
                           (staged_json, json_after)):
        if path.read_bytes() != expected:
            raise RuntimeError('P6_D1_POSTWRITE_READBACK_MISMATCH_' + path.name)
    return {
        'status': 'P6_D1_EXACT_FOUR_MATERIALS_RETIRED_TO_GENERATED_JSON_SOURCE',
        'retired_material_count': 4, 'retired_materials': removed,
        'transport_json_species': sorted(['e', *aliases]),
        'original_electron_lookup_sha256': hashlib.sha256(table_path.read_bytes()).hexdigest(),
        'energy_projection': 'species.e.energy_transport_coef=fluid; 5/3 original',
        'file_sha256': {
            'C0': {'before': hashlib.sha256(first_before).hexdigest(),
                   'after': hashlib.sha256(first.read_bytes()).hexdigest()},
            'overlay': {'before': hashlib.sha256(overlay_before).hexdigest(),
                        'after': hashlib.sha256(overlay.read_bytes()).hexdigest()},
            'JSON': {'before': hashlib.sha256(json_before).hexdigest(),
                     'after': hashlib.sha256(staged_json.read_bytes()).hexdigest()},
        },
        'native_P05': 'NOT_RUN', 'science': 'SCIENCE_HOLD',
    }



def retire_staged_B_d1_observations(chemistry: Path, ordered: list[str]) -> dict:
    """Verify and retain all 14 historical D1 observer pairs in B scratch.

    The original archived inputs are immutable. The validated legacy type
    tokens are subsequently remapped to the Wave2-6-B canonical AuxKernels;
    physical surface-current and Poisson owners remain unchanged. This P2
    scope is not a scientific comparison or P3 approval.
    """
    if (len(ordered) != 10 or len({Path(item).name for item in ordered}) != 10
            or any(Path(item).name != item.split("/")[-1] or
                   not item.endswith(".i") for item in ordered)):
        raise ValueError("S6_B_D1_UNEXPECTED_LAYER_SET")
    spec = importlib.util.spec_from_file_location(
        "issue397_original_d1_contract",
        ROOT / "experiments/Issue395_powered_chemistry_ladder/issue397_d1_instrument.py")
    if spec is None or spec.loader is None:
        raise ValueError("S6_B_D1_ORIGINAL_INSTRUMENT_MISSING")
    instrument = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(instrument)
    donor_spec = importlib.util.spec_from_file_location(
        "issue402_s6_ownership_contract",
        ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry/prepare_hybrid_json_s6.py")
    if donor_spec is None or donor_spec.loader is None:
        raise ValueError("S6_B_D1_OWNER_CONTRACT_MISSING")
    donor = importlib.util.module_from_spec(donor_spec)
    donor_spec.loader.exec_module(donor)
    first = chemistry / Path(ordered[0]).name
    original = first.read_text(encoding="utf-8")
    if not re.search(r"(?m)^    type\s*=\s*PhysicsLowerDSurfaceCurrent\s*$", original):
        raise ValueError("S6_B_D1_PHYSICAL_SURFACE_CURRENT_OWNER_MISSING")
    if "type = PhysicsADSurfaceChargePoissonBC" not in original:
        raise ValueError("S6_B_D1_POISSON_SURFACE_OWNER_MISSING")
    expected = {"wafer_net_current_probe":
                    ("PhysicsLowerDSurfaceCurrentProbeAux",
                     "wafer_net_surface_current_density", None)}
    for name, functor in instrument.FIELDS.items():
        expected[name] = ("PhysicsLowerDSurfaceCurrentProbeAux", functor, None)
    for name, component in instrument.GEOM.items():
        expected[name] = ("PhysicsWaferD1GeometryProbeAux",
                          "wafer_net_surface_current_density", component)
    if len(expected) != 14:
        raise ValueError("S6_B_D1_DIAGNOSTIC_INVENTORY_NOT_FOURTEEN")

    remaining, receipts = original, []
    for name, (kind, functor, component) in expected.items():
        var_params = {"family": "MONOMIAL", "order": "CONSTANT",
                      "block": "wafer_surface"}
        remaining, owner = donor.retire(remaining, "AuxVariables", name, var_params)
        kernel_params = {
            "type": kind, "variable": name,
            "surface_current_density": functor, "block": "wafer_surface",
            "execute_on": "'INITIAL TIMESTEP_END'",
        }
        if component is not None:
            kernel_params.update(potential="potential", component=component)
        remaining, kernel = donor.retire(
            remaining, "AuxKernels", name + "_kernel", kernel_params)
        receipts.append((owner["old_block_sha256"], kernel["old_block_sha256"]))
    # Reject extra unknown retired owners, hidden input consumers or offsets.
    retired_types = ("PhysicsLowerDSurfaceCurrentProbeAux",
                     "PhysicsWaferD1GeometryProbeAux")
    for name in expected:
        rx = r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])"
        if any(re.search(rx, layer) for layer in
               [remaining] + [(chemistry / Path(item).name).read_text(encoding="utf-8")
                               for item in ordered[1:]]):
            raise ValueError("S6_B_D1_UNKNOWN_EXTERNAL_CONSUMER_" + name)
    if any(re.search(r"(?m)^    type\s*=\s*" + re.escape(old) + r"\s*$",
                     remaining) for old in retired_types):
        raise ValueError("S6_B_D1_UNKNOWN_RETIRED_OBSERVER_REMAINS")
    # donor.retire operated on an in-memory copy strictly to verify all 14
    # historic blocks. Preserve the original scratch bytes for the canonical
    # type-token remapper and real P2 observer execution.
    if first.read_text(encoding="utf-8") != original:
        raise ValueError("S6_B_D1_OBSERVATION_PRECHECK_MUTATED_SOURCE")
    return {
        "status": "SCRATCH_ONLY_B_D1_OBSERVERS_VERIFIED_PRESERVED",
        "observer_pairs": len(receipts),
        "native_source_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "native_staged_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "retired_owner_sha256": receipts,
        "B_historical_observation_parity": "NOT_CLAIMED",
        "P3": "NOT_RUN", "science": "SCIENCE_HOLD",
    }


def remap_staged_fem_types(chemistry: Path, ordered: list[str]) -> dict:
    """Rebind only staged input type fields to registered canonical C++ classes."""
    if len(ordered) not in (10, 11):
        raise ValueError("Unexpected S6 input layer count for FEM type remap")
    files = {}
    writes = []
    totals = dict.fromkeys(RENAMED_FEM_KERNEL_TYPES, 0)
    for relative in ordered:
        name = Path(relative).name
        if name != relative.split("/")[-1] or not name.endswith(".i"):
            raise ValueError("Unsafe S6 staged layer name")
        path = chemistry / name
        original = path.read_bytes()
        counts = dict.fromkeys(RENAMED_FEM_KERNEL_TYPES, 0)

        def replace_type(match):
            old = match.group("name")
            counts[old] += 1
            return match.group("indent") + RENAMED_FEM_KERNEL_TYPES[old] + match.group("end")

        updated = _FEM_TYPE_LINE.sub(replace_type, original.decode("utf-8"))
        if _FEM_TYPE_LINE.search(updated):
            raise ValueError("Unconverted archived FEM Kernel type remains")
        for old, count in counts.items():
            totals[old] += count
        output = updated.encode("utf-8")
        writes.append((path, output))
        files[name] = {
            "original_sha256": hashlib.sha256(original).hexdigest(),
            "staged_sha256": hashlib.sha256(output).hexdigest(),
            "type_replacements": {old: count for old, count in counts.items() if count},
        }
    if not any(totals.values()):
        raise ValueError("Expected historical FEM Kernel types in staged S6 inputs")
    for path, output in writes:
        if path.read_bytes() != output:
            path.write_bytes(output)
    return {
        "status": "STAGED_TYPES_RENAMED_WITHOUT_FACTORY_ALIASES",
        "totals": totals,
        "files": files,
    }



def remap_staged_electron_lookup(chemistry: Path, ordered: list[str]) -> dict:
    """Re-use the already mutation-tested, exact historical S6 lookup cutover.

    Only a scratch copy changes. The source B/C deck remains archived and
    immutable; a mismatched table/pressure/temperature/bounds/owner fails
    before any staged file is written.
    """
    if len(ordered) not in (10, 11):
        raise ValueError("Unexpected S6 layer count for electron lookup cutover")
    names = [Path(item).name for item in ordered]
    if (len(set(names)) != len(names)
            or any(name != item.split("/")[-1] or not name.endswith(".i")
                   for name, item in zip(names, ordered))):
        raise ValueError("Unsafe/duplicate S6 lookup layer")

    spec = importlib.util.spec_from_file_location(
        "issue402_s6_lookup_cutover",
        ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry/prepare_s6_run_input.py")
    if spec is None or spec.loader is None:
        raise ValueError("Canonical S6 lookup migration helper missing")
    canonical = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(canonical)

    original = {chemistry / name: (chemistry / name).read_text(encoding="utf-8")
                for name in names}
    revised, receipt = canonical.canonicalize_staged_electron_lookup(original)
    if set(revised) != set(original):
        raise ValueError("Canonical S6 lookup cutover changed the layer inventory")
    changed = [path for path in original if original[path] != revised[path]]
    if (len(changed) != 1 or changed[0].name != names[0]
            or receipt["source_layer"] != names[0]):
        raise ValueError("Canonical S6 lookup owner was not the pinned first layer")
    owner = changed[0]
    if ("type = PhysicsElectronTransportLookupMaterial" in revised[owner]
            or revised[owner].count("type = DDTransportMaterial") <
               original[owner].count("type = DDTransportMaterial") + 1):
        raise ValueError("Retired S6 lookup owner remains after cutover")

    # The helper's exact-source identity and negative mutations are independently
    # tested in tests/test_issue402_s6_electron_transport_compatibility.py.
    for path in changed:
        path.write_text(revised[path], encoding="utf-8")
    receipt["files"] = {
        owner.name: {
            "original_sha256": hashlib.sha256(original[owner].encode("utf-8")).hexdigest(),
            "staged_sha256": hashlib.sha256(revised[owner].encode("utf-8")).hexdigest(),
        }
    }
    return receipt


def remap_staged_wall_owners(chemistry: Path, ordered: list[str]) -> dict:
    """Apply the existing ownership-tested S6 wall migration to scratch only.

    A legacy wall output may be renamed only when its original species,
    density, signed charge, owning Material, and every consumer are verified.
    This is P2 construction compatibility, never proof of P3 wall-law parity.
    """
    if len(ordered) not in (10, 11):
        raise ValueError("Unexpected S6 layer count for wall cutover")
    names = [Path(item).name for item in ordered]
    if (len(names) != len(set(names))
            or any(name != item.split("/")[-1] or not name.endswith(".i")
                   for name, item in zip(names, ordered))):
        raise ValueError("Unsafe or duplicate S6 wall layer")

    spec = importlib.util.spec_from_file_location(
        "issue402_s6_wall_cutover",
        ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry/prepare_s6_run_input.py")
    if spec is None or spec.loader is None:
        raise ValueError("Canonical S6 wall migration helper missing")
    canonical = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(canonical)
    original = {chemistry / name: (chemistry / name).read_text(encoding="utf-8")
                for name in names}
    revised, receipt = canonical.canonicalize_staged_wall_inputs(original)
    if set(original) != set(revised):
        raise ValueError("Canonical S6 wall cutover changed layer inventory")
    if (receipt.get("status") != "SCRATCH_ONLY_SPECIES_WALL_NAMES"
            or not receipt.get("wall_material_owners")
            or receipt.get("P3") != "NOT_RUN"
            or receipt.get("science") != "SCIENCE_HOLD"):
        raise ValueError("Canonical S6 wall owner or scientific HOLD is missing")
    changed = [path for path in original if original[path] != revised[path]]
    if not changed:
        raise ValueError("No original S6 wall owner/consumer was transformed")
    for path in changed:
        path.write_text(revised[path], encoding="utf-8")
    receipt["files"] = {
        path.name: {
            "original_sha256": hashlib.sha256(original[path].encode("utf-8")).hexdigest(),
            "staged_sha256": hashlib.sha256(revised[path].encode("utf-8")).hexdigest(),
        } for path in changed
    }
    return receipt


def remap_staged_sheath_bcs(
        chemistry: Path, ordered: list[str], variant: str) -> dict:
    """Rebind eight proven historical sheath BC owners in disposable B/D input.

    This handles the actual Native P2 archived B names and D canonical names
    separately. Only the registered BC *type* changes: never its variable,
    physical flux, mean-energy input or boundary list. Scientific P3 remains HOLD.
    """
    if variant not in ("B", "D") or len(ordered) not in (10, 11):
        raise ValueError("S6_SHEATH_UNSUPPORTED_VARIANT_OR_LAYER_COUNT")
    names = [Path(item).name for item in ordered]
    if (len(names) != len(set(names))
            or any(name != item.split("/")[-1] or not name.endswith(".i")
                   for name, item in zip(names, ordered))):
        raise ValueError("S6_SHEATH_UNSAFE_OR_DUPLICATE_LAYER")

    spec = importlib.util.spec_from_file_location(
        "issue402_s6_sheath_contract",
        ROOT / "experiments/Issue402_plasma_dsl_g1/chemistry/prepare_hybrid_json_s6.py")
    if spec is None or spec.loader is None:
        raise ValueError("S6_SHEATH_DONOR_CONTRACT_MISSING")
    canonical = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(canonical)

    layers = {name: (chemistry / name).read_text(encoding="utf-8")
              for name in names}
    # The original B/C base owns all eight named BCs. The D no-D1 base does
    # too; reject any shifted ownership or extra archived BC in other layers.
    base_name = names[0]
    legacy_types = tuple(canonical.OLD_SHEATH_TYPES.values())
    if any(re.search(r"(?m)^    type\s*=\s*(?:" +
                     "|".join(map(re.escape, legacy_types)) + r")\s*$",
                     layer)
           for name, layer in layers.items() if name != base_name):
        raise ValueError("S6_SHEATH_SECONDARY_LAYER_RETIRED_OWNER")

    source = layers[base_name]
    matched = []
    for name, (registered, boundary) in canonical.SHEATH_BC_SPEC.items():
        blocks = [
            m for m in canonical.BLOCK.finditer(source)
            if (m.group("name") == name
                and re.findall(r"(?m)^\[([A-Za-z0-9_]+)\]\s*$",
                               source[:m.start()])[-1:] == ["BCs"])
        ]
        if len(blocks) != 1:
            raise ValueError("S6_SHEATH_OWNER_COUNT_" + name + ": " + str(len(blocks)))
        original = blocks[0]
        is_energy = registered == "FEMElectronEnergySheathBC"
        expected = {
            "type": canonical.OLD_SHEATH_TYPES[registered],
            "variable": ("log_energy" if is_energy else
                         ("log_ne" if variant == "B" else "log_e")),
            "wall_number_flux": "e_wall_number_flux",
            "boundary": boundary,
        }
        if is_energy:
            expected["mean_energy"] = "e_energy_eV"
        if canonical.parameters(original.group("body")) != expected:
            raise ValueError("S6_SHEATH_OWNER_IDENTITY_" + name)
        matched.append((original, name, registered))

    if len(matched) != 8:
        raise ValueError("S6_SHEATH_EXPECTED_EIGHT_OWNERS")
    revised = source
    receipts = []
    for original, name, registered in reversed(matched):
        before = original.group(0)
        old = canonical.OLD_SHEATH_TYPES[registered]
        after = before.replace("    type = " + old + "\n",
                               "    type = " + registered + "\n", 1)
        if after == before:
            raise ValueError("S6_SHEATH_TYPE_REPLACEMENT_FAILED_" + name)
        revised = revised[:original.start()] + after + revised[original.end():]
        receipts.append({
            "owner": name,
            "from_type": old,
            "to_type": registered,
            "old_sha256": hashlib.sha256(before.encode()).hexdigest(),
            "new_sha256": hashlib.sha256(after.encode()).hexdigest(),
        })

    if any(re.search(r"(?m)^    type\s*=\s*" + re.escape(old) + r"\s*$", revised)
           for old in legacy_types):
        raise ValueError("S6_SHEATH_UNREGISTERED_TYPE_REMAINS")
    if variant == "D":
        # This P2 option overlays continuity only. Its energy equation is
        # still native log_energy; the hybrid donor generates log_e_energy.
        # Compare a BC-local view only, without rewriting actual D inputs.
        energy_owners = {
            name for name, (kind, _boundary) in canonical.SHEATH_BC_SPEC.items()
            if kind == "FEMElectronEnergySheathBC"
        }

        def hybrid_energy_bc_view(input_text: str) -> str:
            matches = []
            for item in canonical.BLOCK.finditer(input_text):
                if item.group("name") not in energy_owners:
                    continue
                roots = re.findall(
                    r"(?m)^\[([A-Za-z0-9_]+)\]\s*$",
                    input_text[:item.start()])
                if roots[-1:] != ["BCs"]:
                    continue
                if item.group(0).count("    variable = log_energy\n") != 1:
                    raise ValueError("S6_SHEATH_D_NATIVE_ENERGY_OWNER_MISMATCH")
                matches.append(item)
            if len(matches) != 4:
                raise ValueError("S6_SHEATH_D_EXPECTED_FOUR_ENERGY_OWNERS")
            for item in reversed(matches):
                before = item.group(0)
                view = before.replace(
                    "    variable = log_energy\n",
                    "    variable = log_e_energy\n", 1)
                input_text = (input_text[:item.start()] +
                              view + input_text[item.end():])
            return input_text

        donor_revised, donor_receipts = canonical.migrate_exact_s6_fem_sheath(
            hybrid_energy_bc_view(source))
        if (donor_revised != hybrid_energy_bc_view(revised)
                or len(donor_receipts) != 8):
            raise ValueError("S6_SHEATH_DONOR_REPLAY_MISMATCH")

    # All eight blocks are verified before the single scratch write.
    (chemistry / base_name).write_text(revised, encoding="utf-8")
    return {
        "status": "SCRATCH_ONLY_EXACT_EIGHT_SHEATH_BC_TYPE_CUTOVER",
        "variant": variant,
        "source_layer": base_name,
        "owner_count": 8,
        "owners": sorted(receipts, key=lambda row: row["owner"]),
        "original_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "staged_sha256": hashlib.sha256(revised.encode()).hexdigest(),
        "P3": "NOT_RUN", "science": "SCIENCE_HOLD",
    }


def remap_staged_mean_energy(chemistry: Path, ordered: list[str]) -> dict:
    """Rebind only a proven log-molar legacy mean-energy owner in disposable B/D decks.

    Old and new classes both compute exp(log_energy - log_density) [eV]
    in log_molar_eV mode. Their output Functor names differ; rebind all
    consumers in the same staged layer set. Unsupported representations HOLD.
    """
    if len(ordered) not in (10, 11):
        raise ValueError("Unexpected S6 input layer count for mean-energy remap")
    legacy_type = re.compile(
        r"(?m)^[ \t]*type[ \t]*=[ \t]*PhysicsElectronMeanEnergyMaterial[ \t]*$"
    )
    canonical_type = re.compile(
        r"(?m)^[ \t]*type[ \t]*=[ \t]*ElectronEnergyMaterial[ \t]*$"
    )
    owner_block = re.compile(
        r"(?m)^  \[(?P<owner>[A-Za-z_][A-Za-z0-9_]*)\][ \t]*\r?\n"
        r"(?P<body>(?:^    [^\r\n]*\r?\n)+)"
        r"^  \[\][ \t]*(?:\r?\n|$)"
    )
    output_token = re.compile(
        r"(?<![A-Za-z0-9_])mean_en_solved(?![A-Za-z0-9_])"
    )
    original_layers: dict[str, str] = {}
    found = []
    for relative in ordered:
        name = Path(relative).name
        if name != relative.split("/")[-1] or not name.endswith(".i") or name in original_layers:
            raise ValueError("Unsafe or duplicate staged mean-energy layer")
        source = (chemistry / name).read_text(encoding="utf-8")
        original_layers[name] = source
        if canonical_type.search(source):
            raise ValueError("Unexpected existing canonical ElectronEnergyMaterial")
        matches = list(legacy_type.finditer(source))
        if matches:
            if len(matches) != 1:
                raise ValueError("Duplicate archived mean-energy Material types")
            blocks = [m for m in owner_block.finditer(source)
                      if legacy_type.search(m.group("body"))]
            if len(blocks) != 1:
                raise ValueError("Unknown archived mean-energy Material block layout")
            owner = blocks[0]
            pairs = re.findall(
                r"(?m)^    ([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*([^\r\n]+)$",
                owner.group("body"))
            params = dict(pairs)
            if (len(pairs) != len(owner.group("body").splitlines())
                or len(params) != len(pairs)
                or set(params) - {
                    "type", "state_form", "electron_energy_density", "electron_density",
                    "mean_energy_output", "block"}):
                raise ValueError("Unknown archived mean-energy owner parameters")
            if (params.get("type", "").strip() != "PhysicsElectronMeanEnergyMaterial"
                or params.get("state_form", "").strip() != "log_molar_eV"
                or params.get("electron_energy_density", "").strip() not in ("log_energy", "log_e_energy")
                or params.get("electron_density", "").strip() not in ("log_ne", "log_e")
                or params.get("mean_energy_output", "mean_en_solved").strip() != "mean_en_solved"):
                raise ValueError("Archived mean-energy representation or output differs")
            found.append((name, owner))
    if len(found) != 1:
        raise ValueError("Expected exactly one archived mean-energy producer")
    writes = []
    files = {}
    total_references = 0
    for name, source in original_layers.items():
        updated = source
        if name == found[0][0]:
            owner = found[0][1]
            before = owner.group(0)
            after = re.sub(
                r"(?m)^(    type[ \t]*=[ \t]*)PhysicsElectronMeanEnergyMaterial([ \t]*\r?$)",
                r"\1ElectronEnergyMaterial\2", before)
            # New material owns the fixed e_energy_eV name; the retired option
            # mean_energy_output must not leak into the new Native input.
            after = re.sub(
                r"(?m)^    mean_energy_output[ \t]*=[ \t]*mean_en_solved[ \t]*\r?\n",
                "", after)
            if after == before or legacy_type.search(after):
                raise ValueError("Failed to replace archived mean-energy owner")
            updated = source[:owner.start()] + after + source[owner.end():]
        if re.search(
            r"(?m)^[ \t]*(?:property_name|mean_energy_output)[ \t]*=[ \t]*mean_en_solved[ \t]*$",
            updated
        ):
            raise ValueError("Competing archived mean-energy output owner")
        updated, n = output_token.subn("e_energy_eV", updated)
        total_references += n
        files[name] = {
            "original_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "staged_sha256": hashlib.sha256(updated.encode("utf-8")).hexdigest(),
            "functor_reference_replacements": n,
        }
        writes.append((chemistry / name, updated))
    if not total_references:
        raise ValueError("No archived mean-energy Functor consumers found")
    # Validate every layer before writing any scratch file; archives are untouched.
    for target, updated in writes:
        if target.read_text(encoding="utf-8") != updated:
            target.write_text(updated, encoding="utf-8")
    return {
        "status": "SCRATCH_ONLY_LOG_MOLAR_MEAN_ENERGY_CUTOVER",
        "producer_layer": found[0][0],
        "consumer_renames": total_references,
        "files": files,
    }



def check_source(expected_head: str, historical: Path, binary: Path) -> dict:
    if git_head(ROOT) != expected_head or git_head(historical) != HISTORICAL_SHA:
        raise ValueError("Candidate or historical Git source HEAD mismatch")
    if subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "--",
                       "physics_app"], check=False).returncode != 0:
        raise ValueError("Candidate PhysicsApp tracked source is dirty")
    if binary.resolve() != (ROOT / "physics_app/physics-opt").resolve():
        raise ValueError("Binary path is not the exact checkout's PhysicsApp binary")
    if not binary.is_file() or binary.stat().st_size == 0:
        raise ValueError("Native build binary missing/empty")
    mesh = historical / p2.CHEM / "baseline_plasma_plus_unstructured_cover_plus_wafer.msh"
    if not mesh.is_file() or not mesh.stat().st_size:
        raise ValueError("Prepared original S6 public mesh absent")
    if (historical / p2.CHEM / "private_rates").exists():
        raise ValueError("Protected rate folder must not exist in historical checkout")
    provenance_path = ROOT / "experiments/Issue402_plasma_dsl_g1/evidence/native_p1_identity.json"
    if not provenance_path.is_file():
        raise ValueError("Same-job native P1 provenance is absent")
    provenance = json.loads(provenance_path.read_text())
    build_log = ROOT / "experiments/Issue402_plasma_dsl_g1/evidence/native_build.log"
    if (provenance.get("schema") != "issue402.native_p1.job_local.v1" or
        provenance.get("reusable_scope") != "same_exact_head_ci_job_only" or
        provenance.get("source_sha") != expected_head or
        provenance.get("oci_image") != OCI or
        provenance.get("binary_sha256") != sha_file(binary) or
        provenance.get("build_log_sha256") != sha_file(build_log) or
        provenance.get("P1") != "PASS"):
        raise ValueError("Exact-head native P1 build provenance/binary SHA mismatch")
    return {"source_sha": expected_head, "historical_sha": HISTORICAL_SHA,
            "binary_sha256": sha_file(binary), "historical_mesh_sha256": sha_file(mesh),
            "build_image": OCI}


def run_one(binary: Path, binary_sha: str, workspace: Path,
            inputs: list[str], log: Path, timeout_seconds: int) -> dict:
    if sha_file(binary) != binary_sha:
        raise ValueError("Native P1 executable mutated before P2")
    command = ("/workspace/physics_app/physics-opt --check-input -i " +
               " ".join(shlex.quote(x) for x in inputs))
    args = ["docker", "run", "--rm", "--network", "none",
            "--entrypoint", "/bin/bash", "--user", "0:0",
            "--workdir", "/case",
            "--env", "OXYGEN_RESEARCH_400=1",
            "--env", "OXYGEN_RESEARCH_FULL24=0",
            "--env", "OXYGEN_RESEARCH_EI2738_FORMULA=0",
            "--env", "OXYGEN_RESEARCH_QUICK_5MIN=0",
            "--mount", f"type=bind,src={ROOT.resolve()},dst=/workspace,readonly",
            "--mount", f"type=bind,src={workspace.resolve()},dst=/case",
            OCI, "-lc",
            ("set -euo pipefail; source /environment; "
             # Clean the root-owned scratch .jitcache in the isolated case
             # container before host TemporaryDirectory removes the workspace.
             "trap 'rm -rf /case/.jitcache' EXIT; " + command)]
    try:
        result = subprocess.run(args, capture_output=True, text=True,
                                timeout=timeout_seconds, check=False)
        out = result.stdout + "\n" + result.stderr
        log.write_text(out)
        good = result.returncode == 0 and "Syntax OK" in out
        if good:
            classification = "NATIVE_CHECK_INPUT_PASS"
        elif result.returncode == 127 and "error while loading shared libraries" in out:
            classification = "NATIVE_RUNTIME_LINKER_ERROR"
        elif result.returncode == 127:
            classification = "NATIVE_PROCESS_FAILED_BEFORE_INPUT"
        else:
            classification = "NATIVE_CHECK_INPUT_REJECTED"
        return {"P2": "PASS" if good else "HOLD",
                "exit_code": result.returncode, "log_sha256": sha_file(log),
                "syntax_ok": "Syntax OK" in out, "classification": classification}
    except subprocess.TimeoutExpired:
        log.write_text("P2 timeout, no solve was launched\n")
        return {"P2": "HOLD", "classification": "NATIVE_CHECK_INPUT_TIMEOUT",
                "log_sha256": sha_file(log)}


def persist_report(evidence: Path, report: dict) -> None:
    """Atomic checkpoint independent of root-owned Native scratch cleanup."""
    evidence.mkdir(parents=True, exist_ok=True)
    target = evidence / "issue402_option_s6_p2_status.json"
    pending = evidence / "issue402_option_s6_p2_status.json.tmp"
    pending.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    os.replace(pending, target)


def execute(historical: Path, binary: Path, expected_head: str,
            evidence: Path, timeout_seconds: int = 1200) -> dict:
    validate_overlay()
    gate_file = evidence / "option_s6_environment.json"
    if not gate_file.is_file():
        raise ValueError("Independent public P0/environment gate evidence missing")
    gate = json.loads(gate_file.read_text())
    if (gate.get("source_sha") != expected_head or gate.get("image") != OCI or
        any(gate.get(k) != "PASS" for k in
            ("public_p0", "docker_mount", "root_scratch_create_and_cleanup", "host_cleanup"))):
        raise ValueError("Independent P0/environment gate evidence does not match exact source/OCI")
    public = p2.preflight(ROOT)
    identity = check_source(expected_head, historical, binary)
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"gate": "Issue402 S6 option-only public P2",
              "status": "HOLD", "science": "SCIENCE_HOLD", "P0": "PASS",
              "P1": "PASS_SOURCE_BOUND_BINARY",
              "P2": "HOLD", "P3": "NOT_RUN", "P4": "NOT_RUN",
              "identity": identity,
              "original_immutable_candidate_sha": p2.PINNED_CANDIDATE,
              "public_deck_manifest_sha256": sha_file(
                  ROOT / p2.DECKS / "manifest.json"),
              "option_overlay_sha256": OVERLAY_SHA256,
              "checks": {}}
    if public.get("P0") != "PASS":
        raise ValueError("Public reference P0 is not PASS")
    persist_report(evidence, report)
    try:
        with tempfile.TemporaryDirectory(prefix="issue402_option_s6_p2_",
                                         dir=os.getenv("RUNNER_TEMP", None)) as tmp:
            root = Path(tmp)
            manifest = json.loads((ROOT / p2.DECKS / "manifest.json").read_text())
            for case in CASES:
                report["checks"][case] = {}
                for variant in VARIANTS:
                    label = f"{case}_{variant}"
                    staged = root / label
                    try:
                        old_variant = "B" if variant == "B" else "C"
                        scratch_migration = None
                        # Original B stays byte-identical. D starts directly
                        # from the pinned debug-free physics base; no injection
                        # and no subsequent stripping of obsolete D1 probes.
                        d_base = (ROOT / "experiments/Issue402_plasma_dsl_g1/native/"
                                  "s6_c0_physics_base_no_d1.i") if variant == "D" else None
                        ordered = p2.stage(ROOT, historical, case, old_variant,
                                           staged, manifest, d_base_source=d_base)
                        scratch_retired_B = None
                        if variant == "B":
                            scratch_retired_B = retire_staged_B_d1_observations(
                                staged / p2.CHEM, ordered)
                        if variant == "D":
                            overlay = staged / p2.CHEM / "migrated_continuity.i"
                            # Rewrite only the temporary D copies of the ten
                            # archived input layers. B and source archives are untouched.
                            # The resulting D input is a syntax-only migration candidate.
                            if not overlay.is_file():
                                raise ValueError("Expected original C migration sidecar is missing")
                            scratch_migration = canonicalize_staged_D_inputs(
                                staged / p2.CHEM, ordered)
                            # The FileName parameter is resolved from the staged input directory.
                            # Only a disposable JSON copy is created; the repository file is immutable.
                            shutil.copy2(ROOT / "experiments/Issue402_plasma_dsl_g1/plasma_species_only.json",
                                         staged / p2.CHEM / "plasma_species_only.json")
                            scratch_initials = reconcile_staged_D_json_initials(
                                staged / p2.CHEM, ordered)
                            overlay.write_text(OVERLAY, encoding="utf-8")
                            if sha_file(overlay) != OVERLAY_SHA256:
                                raise ValueError("Staged D sidecar SHA is incorrect")
                        scratch_types = remap_staged_fem_types(staged / p2.CHEM, ordered)
                        scratch_lookup = remap_staged_electron_lookup(staged / p2.CHEM, ordered)
                        scratch_wall = remap_staged_wall_owners(staged / p2.CHEM, ordered)
                        scratch_mean_energy = remap_staged_mean_energy(staged / p2.CHEM, ordered)
                        scratch_sheath = remap_staged_sheath_bcs(staged / p2.CHEM, ordered, variant)
                        scratch_transport = None
                        if variant == "D":
                            scratch_transport = cutover_staged_D_transport_owners(
                                staged / p2.CHEM, ordered)
                        log = evidence / f"S6_{label}_P2.log"
                        report["checks"][case][variant] = run_one(
                            binary, identity["binary_sha256"], staged, ordered,
                            log, timeout_seconds)
                        report["checks"][case][variant]["layers"] = len(ordered)
                        report["checks"][case][variant]["scratch_fem_type_remap"] = scratch_types
                        report["checks"][case][variant]["scratch_lookup_cutover"] = scratch_lookup
                        report["checks"][case][variant]["scratch_wall_cutover"] = scratch_wall
                        report["checks"][case][variant]["scratch_mean_energy_cutover"] = scratch_mean_energy
                        report["checks"][case][variant]["scratch_sheath_bc_cutover"] = scratch_sheath
                        if scratch_retired_B is not None:
                            report["checks"][case][variant]["scratch_B_d1_retirement"] = scratch_retired_B
                        if scratch_migration is not None:
                            report["checks"][case][variant]["scratch_migration"] = scratch_migration
                            report["checks"][case][variant]["scratch_json_initials"] = scratch_initials
                            report["checks"][case][variant]["scratch_transport_owner_cutover"] = scratch_transport
                    except Exception as exc:
                        report["checks"][case][variant] = {
                            "P2": "HOLD", "classification": type(exc).__name__,
                            "error": str(exc)[:250]}
                    persist_report(evidence, report)

            checks = [report["checks"][c][v]["P2"] for c in CASES for v in VARIANTS]
            report["P2"] = "PASS" if checks == ["PASS"] * 4 else "HOLD"
            report["status"] = "P2_PASS_CLEANUP_PENDING" if report["P2"] == "PASS" else "HOLD"
            report["cleanup"] = "PENDING"
            persist_report(evidence, report)

    except OSError as exc:
        # Never erase actual P2 results when host cleanup of OCI-owned scratch
        # fails. The overall G2 gate still HOLDs until cleanup is resolved.
        report["cleanup"] = "HOLD"
        report["cleanup_error_class"] = type(exc).__name__
        report["status"] = "HOLD_INFRASTRUCTURE_CLEANUP"
        persist_report(evidence, report)
        return report
    report["cleanup"] = "PASS"
    report["status"] = "PASS" if report["P2"] == "PASS" else "HOLD"
    persist_report(evidence, report)
    return report

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = execute(args.historical.resolve(), args.binary.resolve(),
                         args.expected_head, args.evidence.resolve())
        exit_code = 0 if (result["P2"] == "PASS" and result.get("cleanup") == "PASS" and result["status"] == "PASS") else 3
    except Exception as exc:
        result = {"gate": "Issue402 S6 option-only public P2",
                  "status": "HOLD", "P2": "HOLD", "P3": "NOT_RUN", "P4": "NOT_RUN",
                  "science": "SCIENCE_HOLD",
                  "classification": type(exc).__name__, "blocker": str(exc)[:400]}
        exit_code = 3
    args.evidence.mkdir(parents=True, exist_ok=True)
    (args.evidence / "issue402_option_s6_p2_status.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
