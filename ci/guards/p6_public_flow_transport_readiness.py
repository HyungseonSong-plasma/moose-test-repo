"""Read-only P6-D1 Public-D/FLOW transport cutover gate.

This is a diagnostic, not a migration or a replacement of native P05.
It refuses a superficial JSON-only repair that would create double Functor
providers or lose the historical electron 5/3 energy projection.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import re

CHARGED = ("e", "O2p", "Om", "Op")
# Exact PR #665 HEAD 74a2b0f source blobs; this gate is read-only and
# explicitly does not generalize to a moving integration branch.
PINNED_GIT_BLOBS = {
    "plasma_species_only.json": "c563f54b4914773f153b170fb8b5b63f2687c170",
    "public_option_s6_p2.py": "a6414baf70590b79f4b4ee4cb16c4b9039355f40",
    "prepare_s6_run_input.py": "60a12878a26969fdf1ae26eab47694244b601634",
    "DDContinuityEq.C": "13b25226d463b8fd1e4acaee16358f8f17d710a0",
    "s6_c0_physics_base_no_d1.i": "793f3f24bc95bf71d0b2537288cb2ecc8a5f74fa",
}


def git_blob_sha1(blob: bytes) -> str:
    header = ("blob " + str(len(blob)) + "\0").encode()
    return hashlib.sha1(header + blob).hexdigest()



def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def option_overlay(py_source: str) -> str:
    tree = ast.parse(py_source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "OVERLAY"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("P6_D1_PUBLIC_OPTION_OVERLAY_MISSING")


def selected_species(overlay: str) -> tuple[str, ...]:
    groups = []
    for key in ("fem_species", "fvm_species"):
        matches = re.findall(r"(?m)^\s*" + key + r"\s*=\s*'([^']+)'\s*$", overlay)
        if len(matches) != 1:
            raise ValueError("P6_D1_BAD_" + key.upper())
        groups.extend(matches[0].split())
    if tuple(groups) != CHARGED:
        raise ValueError("P6_D1_CHARGED_SPECIES_CHANGED")
    return tuple(groups)


def assess(*, data: dict, selected: tuple[str, ...], manual_owners: set[str],
           physics_generates: bool, has_energy_action: bool,
           manual_e_fluid_energy: bool, legacy_ion_owners: bool) -> dict:
    """Static owner graph; not a C++ Warehouse observation."""
    species = data.get("species")
    if not isinstance(species, dict) or not set(selected).issubset(species):
        raise ValueError("P6_D1_SPECIES_IDENTITY_CHANGED")
    missing = sorted(x for x in selected if "transport_coef" not in species[x])
    for x in selected:
        rec = species[x]
        if not isinstance(rec, dict) or not isinstance(rec.get("charge_number"), int):
            raise ValueError("P6_D1_BAD_SPECIES_SCHEMA_" + x)
    generated = set(selected) if physics_generates else set()
    overlaps = sorted(generated.intersection(manual_owners))
    problems = []
    if missing:
        problems.append("MISSING_TRANSPORT_JSON")
    if overlaps:
        problems.append("DUPLICATE_DDTRANSPORT_PRODUCER")
    if physics_generates and "e" in generated and "e" not in manual_owners and not has_energy_action:
        problems.append("ELECTRON_5_OVER_3_ENERGY_PROJECTION_NOT_PROVEN")
    if physics_generates and legacy_ion_owners:
        problems.append("P05_LEGACY_ION_FV_OWNERS_NOT_RETIRED")
    if not manual_e_fluid_energy and "e" in manual_owners:
        problems.append("HISTORICAL_MANUAL_E_ENERGY_CLOSURE_MISSING")
    return {
        "status": "HOLD" if problems else "SOURCE_READY_NATIVE_NOT_RUN",
        "missing_transport_species": missing,
        "overlapping_manual_and_generated": overlaps,
        "errors": problems,
        "generated_transport_owners_expected": sorted(generated),
        "native_p2": "NOT_RUN",
        "science": "SCIENCE_HOLD",
    }


def audit_repo(root: Path) -> dict:
    pilot = root / "experiments/Issue402_plasma_dsl_g1"
    js_path = pilot / "plasma_species_only.json"
    opt_path = pilot / "public_option_s6_p2.py"
    lookup_path = pilot / "chemistry/prepare_s6_run_input.py"
    phys_path = root / "physics_app/src/physics/plasma/DDContinuityEq.C"
    base_path = pilot / "native/s6_c0_physics_base_no_d1.i"
    texts = {p.name: p.read_bytes() for p in (js_path, opt_path, lookup_path, phys_path, base_path)}
    for name, expected in PINNED_GIT_BLOBS.items():
        if git_blob_sha1(texts[name]) != expected:
            raise ValueError("P6_D1_EXACT_SOURCE_BLOB_CHANGED_" + name)
    overlay = option_overlay(texts[opt_path.name].decode())
    selected = selected_species(overlay)
    lookup = texts[lookup_path.name].decode()
    physics = texts[phys_path.name].decode()
    base = texts[base_path.name].decode()
    if not all((f"[{name}_species_transport_alias]" in overlay and
                "type = DDTransportMaterial" in overlay) for name in ("O2p", "Om", "Op")):
        raise ValueError("P6_D1_THREE_MANUAL_ION_MATERIALS_NOT_PINNED")
    if not all(token in lookup for token in (
        '"electron_transport"', '"    fluid_energy = true\\n"',
        '"    type = DDTransportMaterial\\n"',
        '"    bounds_policy = clamp\\n"'
    )):
        raise ValueError("P6_D1_MANUAL_E_LOOKUP_IDENTITY_DRIFT")
    if not all(token in physics for token in (
        'getProblem().addFunctorMaterial(type, name() + "_" + id + "_transport_coefficients", params)',
        'energy.front()->getParam<MooseEnum>("transport_coefficient") == "fluid"',
        'if (!mechanism.ddTransport(id))',
        'const bool generate_kernels = !getParam<bool>("dont_create_kernels");'
    )):
        raise ValueError("P6_D1_PHYSICS_OWNER_CONTRACT_CHANGED")
    if "[ni_time]" not in base or "[nm_time]" not in base or "[nop_time]" not in base:
        raise ValueError("P6_D1_LEGACY_ION_OWNER_CONTRACT_CHANGED")
    data = json.loads(texts[js_path.name])
    original_sha = {str(p.relative_to(root)): sha256(p.read_bytes())
                    for p in (js_path, opt_path, lookup_path, phys_path, base_path)}
    result = assess(data=data, selected=selected,
                    manual_owners=set(CHARGED), physics_generates=True,
                    has_energy_action="[Energy]" in overlay,
                    manual_e_fluid_energy=True, legacy_ion_owners=True)
    after_sha = {str(p.relative_to(root)): sha256(p.read_bytes())
                 for p in (js_path, opt_path, lookup_path, phys_path, base_path)}
    if after_sha != original_sha:
        raise RuntimeError("P6_D1_SOURCE_CHANGED_DURING_AUDIT")
    result.update({"schema": "issue672.p6_d1.read_only_transport_owner_gate.v1",
                   "selected": list(selected), "verified_source_sha256": original_sha,
                   "no_source_writes": True,
                   "warning": "This gate is a static model, not an observed Warehouse."})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(audit_repo(args.repo), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
