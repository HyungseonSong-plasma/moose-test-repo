#!/usr/bin/env python3
"""Repository-wide route inventory for species initial-volume and inlet mass fractions.

Scans every text source/config in ACTIVE tree roots, not merely a handpicked
shortlist. Reports ALL matching paths and line numbers for reproducible review.
Archives, binary files and documentation prose are deliberately outside the
active implementation inventory; the markdown design report covers history.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
ROOTS = ("physics_app", "experiments", "physics_harness", "tests", "ci")
SUFFIXES = {".py", ".json", ".i", ".C", ".h", ".yml", ".yaml"}
SKIP_DIRS = {"archive", ".git", ".venv", "__pycache__", ".pytest_cache"}
PATTERNS = {
    "species_schema_and_json": re.compile(
        r'initial_vol_mass_fraction|initial_inlet_mass_fraction|'
        r'charge_number|molar_mass_kg_mol|\bgas_state\b'
    ),
    "bulk_initialization": re.compile(
        r'\binitial_condition\b|FVConstantIC|ConstantIC|FunctionIC|'
        r'\bInitialConditions\b|\binit(?:ial)?_mass_fraction\b'
    ),
    "inlet_boundary_and_feed": re.compile(
        r'\binlet\b|inlet_|\bFVBCs\b|FVDirichletBC|\bfeed\b|'
        r'mass_flux|\bsccm\b', re.IGNORECASE
    ),
    "live_species_composition": re.compile(
        r'mass_fractions?|\bY_[A-Za-z0-9_]+\b|\bw_O2\b|'
        r'ion_mass_fractions|heavy_mass_fractions|Yin_', re.IGNORECASE
    ),
    "gas_eos_and_closure": re.compile(
        r'\brho_g\b|\bM_mix\b|\bn_g\b|\bP_g\b|\bT_g\b|'
        r'\bgas_pressure\b|\bgas_temperature\b|'
        r'mean_molar_mass|mixture_density|PHYSICS_CONSTANTS::R|ideal_gas'
    ),
    "rate_transport_charge_consumers": re.compile(
        r'HRateCoefMaterial|EIRateCoefMaterial|SurfaceReactionMaterial|'
        r'NVTransportMaterial|DDTransportMaterial|PhysicsPlasmaChargeDensityMaterial|'
        r'PhysicsFVHeavyMassElectromigrationCorrection|PhysicsIonWallFluxMaterial'
    ),
}


def iter_active_sources():
    for root in ROOTS:
        base = ROOT / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
                continue
            if path.is_file() and path.suffix in SUFFIXES:
                yield path


def audit():
    seen = []
    routes = defaultdict(list)
    retired_json = []
    json_species = []
    for path in iter_active_sources():
        rel = path.relative_to(ROOT).as_posix()
        seen.append(rel)
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        lines = content.splitlines()
        for category, pattern in PATTERNS.items():
            matched = [n for n, line in enumerate(lines, 1) if pattern.search(line)]
            if matched:
                routes[category].append({"path": rel, "lines": matched})
        if path.suffix == ".json":
            try:
                obj = json.loads(content)
            except ValueError:
                continue
            if isinstance(obj, dict):
                if "gas_state" in obj:
                    retired_json.append(rel)
                if isinstance(obj.get("species"), dict):
                    fields = {
                        name: {
                            "has_molar_mass": "molar_mass_kg_mol" in spec,
                            "initial_volume": spec.get("initial_vol_mass_fraction"),
                            "initial_inlet": spec.get("initial_inlet_mass_fraction"),
                        }
                        for name, spec in obj["species"].items()
                        if isinstance(spec, dict) and (
                            "initial_vol_mass_fraction" in spec or
                            "initial_inlet_mass_fraction" in spec
                        )
                    }
                    if fields:
                        json_species.append({"path": rel, "species": fields})

    return {
        "scanned_source_file_count": len(seen),
        "scanned_roots": list(ROOTS),
        "matched_route_counts": {
            name: len(routes[name]) for name in PATTERNS
        },
        "routes": dict(routes),
        "species_initial_data_json": json_species,
        "retired_top_level_gas_state_json": retired_json,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--fail-on-legacy", action="store_true")
    args = parser.parse_args()
    result = audit()
    print("ISSUE402_COMPOSITION_ROUTE_INVENTORY")
    print("SCANNED_SOURCE_FILES", result["scanned_source_file_count"])
    for name, count in result["matched_route_counts"].items():
        print(f"{name.upper()}_FILES", count)
        hot = [item["path"] for item in result["routes"].get(name, [])
               if item["path"].startswith("physics_app/src/")]
        for path in hot[:25]:
            print(f"  {name}: {path}")
    print("JSON_SPECIES_INITIAL_CATALOGUES", len(result["species_initial_data_json"]))
    print("RETIRED_GAS_STATE_JSON", len(result["retired_top_level_gas_state_json"]))
    for path in result["retired_top_level_gas_state_json"]:
        print("RETIRED_GAS_STATE_FOUND", path)

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(result, indent=2) + "\n")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            "# Issue402 full active source routing inventory",
            "",
            f"Scanned {result['scanned_source_file_count']} source/config files.",
            "The paths below include every match in the declared active roots. "
            "Historical archives and prose documents are outside this automatic scan.",
            "",
        ]
        for name, matches in result["routes"].items():
            rows += [f"## {name} ({len(matches)} files)", ""]
            rows += [f"- \x60{entry['path']}\x60 (lines {', '.join(map(str, entry['lines'][:16]))})"
                     for entry in matches]
            rows.append("")
        rows += ["## Species initial records", "",
                 "\x60" + json.dumps(result["species_initial_data_json"], indent=2) + "\x60",
                 "", "## Retired top-level gas_state records", ""]
        rows += [f"- {path}" for path in result["retired_top_level_gas_state_json"]]
        args.markdown_output.write_text("\n".join(rows) + "\n")

    if args.fail_on_legacy and result["retired_top_level_gas_state_json"]:
        raise SystemExit("FAIL: retired top-level gas_state JSON entry found")
    print("ISSUE402_COMPOSITION_ROUTE_INVENTORY_PASS")


if __name__ == "__main__":
    main()
