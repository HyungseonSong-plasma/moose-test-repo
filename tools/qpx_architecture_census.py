#!/usr/bin/env python3
"""Machine-checkable architecture census for capability-oriented QPX ownership."""
from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "qpx_harness"
OWNERSHIP_PATH = ROOT / "docs" / "development" / "2026-09-01_issue73_recipe_ownership.json"

# Transitional census vocabulary: retained legacy capability packages and the
# canonical responsibility-oriented packages introduced by #130/#133 are both
# classified. Presence here means the package has an explicit responsibility;
# it does not make legacy and canonical owners semantically equivalent.
CAPABILITY_DIRS = {
    "adapters",
    "analysis",
    "application",
    "cpp",
    "diagnose",
    "diagnostics",
    "dmix",
    "domains",
    "evidence",
    "execution",
    "inventory",
    "models",
    "moose",
    "observation",
    "ontology",
    "performance",
    "petsc",
    "planning",
    "provenance",
    "reasoning",
    "spec",
    "specification",
    "transforms",
    "validation",
}

# Preserve the pre-#129 dependency-edge scope. Expanding canonical ownership
# classification must not silently activate unrelated legacy dependency debt.
GENERIC_ISSUE_EDGE_DIRS = {
    "analysis",
    "cpp",
    "diagnostics",
    "evidence",
    "execution",
    "moose",
    "performance",
    "petsc",
    "spec",
    "transforms",
}

ISSUE_NAME_RE = re.compile(r"(?:^|/)(?:issue\d+|coupling_evr\d+)(?:_|/|\.py)", re.IGNORECASE)
FORBIDDEN_PRODUCTION_NAMESPACE_RE = re.compile(
    r"^qpx_harness/(?:issue\d+(?:_|/|\.py)|coupling_evr\d+(?:_|/|\.py))",
    re.IGNORECASE,
)
FORBIDDEN_GENERIC_PREFIXES = (
    "recipes",
    "qpx_harness.issue",
    "qpx_harness.electron_inventory_nullspace",
    "qpx_harness.coupling_evr",
)


def _python_files(root: Path) -> list[Path]:
    return [
        path for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _recipe_ownership() -> dict[str, dict]:
    payload = json.loads(OWNERSHIP_PATH.read_text())
    recipes = payload.get("recipes")
    if not isinstance(recipes, dict):
        raise RuntimeError("recipe ownership artifact is malformed")
    return recipes


def classify(path: Path, recipe_map: dict[str, dict]) -> str:
    rel = _rel(path)
    parts = Path(rel).parts
    if parts[0] == "recipes":
        if rel == "recipes/__init__.py":
            return "LEGACY_COMPATIBILITY_ONLY"
        return "LEGACY_COMPATIBILITY_ONLY" if rel in recipe_map else "UNCLASSIFIED"
    if parts[0] == "bin":
        return "CLI_PRESENTATION"
    if parts[0] == "scripts":
        return "RETIREMENT_CANDIDATE"
    if parts[0] != "qpx_harness":
        return "UNCLASSIFIED"
    if len(parts) >= 3 and parts[1] in CAPABILITY_DIRS:
        return "CAPABILITY_OWNER"
    if len(parts) >= 3 and parts[1] == "cli":
        return "CLI_PRESENTATION"
    if ISSUE_NAME_RE.search(rel):
        return "ISSUE_SPECIFIC_POLICY"
    if rel == "qpx_harness/__init__.py":
        return "PACKAGE_ENTRYPOINT"
    return "UNCLASSIFIED"


def imported_modules(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            if node.level:
                package = path.relative_to(ROOT).with_suffix("").parts[:-1]
                keep = max(0, len(package) - node.level + 1)
                base = ".".join(package[:keep])
                module = ".".join(part for part in (base, node.module) if part)
            else:
                module = node.module
            modules.add(module)
    return tuple(sorted(modules))


def generic_issue_edges(files: list[Path]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for path in files:
        rel = _rel(path)
        parts = Path(rel).parts
        if len(parts) < 3 or parts[0] != "qpx_harness" or parts[1] not in GENERIC_ISSUE_EDGE_DIRS:
            continue
        for module in imported_modules(path):
            if module.startswith(FORBIDDEN_GENERIC_PREFIXES):
                edges.append({"source": rel, "target": module})
    return edges


def forbidden_production_namespaces(files: list[Path]) -> list[str]:
    """Return issue/campaign-numbered Python ownership under qpx_harness/."""
    return sorted(
        _rel(path)
        for path in files
        if FORBIDDEN_PRODUCTION_NAMESPACE_RE.match(_rel(path))
    )


def module_package_collisions() -> list[str]:
    """Return direct qpx_harness names that exist as both module and package."""
    modules = {
        path.stem
        for path in HARNESS.glob("*.py")
        if path.name != "__init__.py"
    }
    packages = {
        path.name
        for path in HARNESS.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    }
    return sorted(modules & packages)


def root_modules() -> list[str]:
    """Return unowned direct Python modules at the qpx_harness package root."""
    return sorted(
        _rel(path)
        for path in HARNESS.glob("*.py")
        if path.name != "__init__.py"
    )


def build_census() -> dict:
    recipe_map = _recipe_ownership()
    harness_files = _python_files(HARNESS)
    recipe_files = _python_files(ROOT / "recipes")
    bin_files = _python_files(ROOT / "bin") if (ROOT / "bin").is_dir() else []
    script_files = _python_files(ROOT / "scripts") if (ROOT / "scripts").is_dir() else []
    files = harness_files + recipe_files + bin_files + script_files
    records = [
        {"path": _rel(path), "class": classify(path, recipe_map)}
        for path in files
    ]
    unclassified = [record["path"] for record in records if record["class"] == "UNCLASSIFIED"]
    recipe_paths = sorted(_rel(path) for path in recipe_files if path.name != "__init__.py")
    expected_recipes = sorted(recipe_map)
    recipe_set_ok = recipe_paths == expected_recipes
    edges = generic_issue_edges(harness_files)
    forbidden_namespaces = forbidden_production_namespaces(harness_files)
    collisions = module_package_collisions()
    direct_root_modules = root_modules()
    class_counts = dict(Counter(record["class"] for record in records))
    return {
        "status": (
            "PASS"
            if not unclassified
            and recipe_set_ok
            and not edges
            and not forbidden_namespaces
            and not collisions
            and not direct_root_modules
            else "FAIL"
        ),
        "production_owner_count": len(records),
        "class_counts": class_counts,
        "owners": records,
        "unclassified": unclassified,
        "recipe_set": recipe_paths,
        "recipe_set_expected": expected_recipes,
        "recipe_set_ok": recipe_set_ok,
        "root_recipes_class": "LEGACY_COMPATIBILITY_ONLY",
        "generic_to_issue_edges": edges,
        "forbidden_production_namespaces": forbidden_namespaces,
        "module_package_collisions": collisions,
        "root_modules": direct_root_modules,
        "scripts_python_files": [_rel(path) for path in script_files],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx-architecture-census")
    parser.add_argument("--json-out")
    args = parser.parse_args(argv)
    result = build_census()
    if args.json_out:
        out = Path(args.json_out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"ISSUE70_PRODUCTION_OWNERS: {result['production_owner_count']}")
    print(f"ISSUE70_UNCLASSIFIED: {len(result['unclassified'])}")
    print(f"ISSUE70_GENERIC_TO_ISSUE_EDGES: {len(result['generic_to_issue_edges'])}")
    print(f"ISSUE128_FORBIDDEN_PRODUCTION_NAMESPACES: {len(result['forbidden_production_namespaces'])}")
    print(f"ISSUE70_MODULE_PACKAGE_COLLISIONS: {len(result['module_package_collisions'])}")
    print(f"ISSUE129_ROOT_MODULES: {len(result['root_modules'])}")
    for path in result["root_modules"]:
        print(f"ISSUE129_ROOT_MODULE: {path}")
    print(f"ISSUE129_ROOT_SURFACE: {'PASS' if not result['root_modules'] else 'FAIL'}")
    print(f"ISSUE70_RECIPE_SET: {'PASS' if result['recipe_set_ok'] else 'FAIL'}")
    print(f"ISSUE138_ROOT_RECIPES_CLASS: {result['root_recipes_class']}")
    print(f"ISSUE70_ARCHITECTURE_CENSUS: {result['status']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
