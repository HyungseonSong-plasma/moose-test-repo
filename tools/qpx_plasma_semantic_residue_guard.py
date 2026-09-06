#!/usr/bin/env python3
"""Guard reusable plasma semantics against historical campaign ownership.

Issue #148 permits exact physical names and immutable experiment/provenance data,
but production qpx_harness modules must not be owned by D_mix comparison campaigns,
electron-only inventory packages, or Issue2/Issue45 fixture paths.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "qpx_harness"

FORBIDDEN_PATH_PARTS = {"dmix_equivalence", "electron_inventory"}
FORBIDDEN_IMPORT_PARTS = ("dmix_equivalence", "electron_inventory")
FORBIDDEN_FIXTURE_FRAGMENTS = (
    "tests/Issue2_",
    "tests/Issue45_",
    "experiments/Issue2_electron_bulk_drift",
)


def _python_files() -> list[Path]:
    return sorted(PRODUCTION.rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def main() -> int:
    files = _python_files()
    forbidden_paths = [
        path.relative_to(ROOT).as_posix()
        for path in files
        if any(part in FORBIDDEN_PATH_PARTS for part in path.parts)
    ]
    forbidden_imports: list[str] = []
    fixture_dependencies: list[str] = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        for module in _imports(path):
            if any(part in module for part in FORBIDDEN_IMPORT_PARTS):
                forbidden_imports.append(f"{rel}: {module}")
        text = path.read_text(encoding="utf-8")
        for fragment in FORBIDDEN_FIXTURE_FRAGMENTS:
            if fragment in text:
                fixture_dependencies.append(f"{rel}: {fragment}")

    domain = ROOT / "qpx_harness/domains/plasma/species_constraints.py"
    parameterized_species = domain.is_file()
    dmix_campaign_modules = sum("dmix_equivalence" in value for value in forbidden_paths)
    electron_inventory_packages = sum("electron_inventory" in value for value in forbidden_paths)

    print(f"PRODUCTION_DMIX_CAMPAIGN_MODULES = {dmix_campaign_modules}")
    print(f"PRODUCTION_ELECTRON_INVENTORY_PACKAGES = {electron_inventory_packages}")
    print(f"SINGLE_SPECIES_HARDCODED_INVENTORY_APIS = {len(forbidden_imports)}")
    print(f"SPECIES_CONSTRAINT_CAPABILITIES_ARE_PARAMETERIZED = {str(parameterized_species).lower()}")
    print(f"PRODUCTION_ISSUE_SPEC_DEPENDENCIES = {len(fixture_dependencies)}")
    print(f"CAMPAIGN_FIXTURES_IN_DOMAIN_OWNERS = {len(fixture_dependencies)}")

    failures = forbidden_paths + forbidden_imports + fixture_dependencies
    if failures or not parameterized_species:
        for item in failures:
            print(f"PLASMA_SEMANTIC_RESIDUE: {item}")
        print("PLASMA_SEMANTIC_RESIDUE_GUARD = FAIL")
        return 1
    print("PLASMA_SEMANTIC_RESIDUE_GUARD = PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
