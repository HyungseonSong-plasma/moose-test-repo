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


def sha(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def remove_one(text: str, name: str, variable: str, functor: str) -> str:
    match_list = [m for m in KERNEL.finditer(text) if m.group("name") == name]
    if len(match_list) != 1:
        raise ValueError(f"{name}: expected one original Kernel, found {len(match_list)}")
    m = match_list[0]
    prefix = text[:m.start()]
    # Require the specific Kernels block to be active at this position.
    if not re.search(r"(?m)^\[Kernels\][ \t]*\r?$", prefix):
        raise ValueError(f"{name}: missing enclosing Kernels block")
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
