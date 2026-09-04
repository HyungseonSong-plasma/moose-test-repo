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

# #143 compatibility-retirement scope. These are not canonical responsibility
# owners even while their physical namespaces remain during bounded migration.
LEGACY_NAMESPACE_PATHS = {
    "qpx_harness.cpp": ROOT / "qpx_harness" / "cpp",
    "qpx_harness.diagnose": ROOT / "qpx_harness" / "diagnose",
    "qpx_harness.dmix": ROOT / "qpx_harness" / "dmix",
    "qpx_harness.inventory": ROOT / "qpx_harness" / "inventory",
    "qpx_harness.performance": ROOT / "qpx_harness" / "performance",
    "qpx_harness.spec": ROOT / "qpx_harness" / "spec",
    "recipes": ROOT / "recipes",
}
SCAN_ROOTS = (
    ROOT / "qpx_harness",
    ROOT / "tests",
    ROOT / "experiments",
    ROOT / "recipes",
    ROOT / "bin",
    ROOT / "tools",
)


def _python_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [
        path for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def _repository_python_files() -> list[Path]:
    files = {path for root in SCAN_ROOTS for path in _python_files(root)}
    return sorted(files)


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


def _relative_import_base(path: Path, level: int, module: str | None) -> str:
    package = path.relative_to(ROOT).with_suffix("").parts[:-1]
    keep = max(0, len(package) - level + 1)
    base = ".".join(package[:keep])
    return ".".join(part for part in (base, module or "") if part)


def import_references(path: Path) -> tuple[str, ...]:
    """Return static and literal dynamic import references used by ``path``."""
    tree = ast.parse(path.read_text(), filename=str(path))
    references: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            references.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = (
                _relative_import_base(path, node.level, node.module)
                if node.level
                else (node.module or "")
            )
            if base:
                references.add(base)
            for alias in node.names:
                if alias.name == "*":
                    continue
                candidate = ".".join(part for part in (base, alias.name) if part)
                if candidate:
                    references.add(candidate)
        elif isinstance(node, ast.Call) and node.args:
            first = node.args[0]
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                continue
            is_builtin_import = isinstance(node.func, ast.Name) and node.func.id == "__import__"
            is_importlib = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "importlib"
            )
            if is_builtin_import or is_importlib:
                references.add(first.value)
    return tuple(sorted(references))


def imported_modules(path: Path) -> tuple[str, ...]:
    """Compatibility wrapper for dependency-edge callers."""
    return import_references(path)


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


def _caller_class(rel: str) -> str:
    if rel.startswith("qpx_harness/"):
        return "production"
    if rel.startswith("tests/"):
        return "test"
    if rel.startswith("experiments/") or rel.startswith("recipes/"):
        return "historical"
    if rel.startswith("bin/"):
        return "operator"
    if rel.startswith("tools/"):
        return "developer"
    return "other"


def _inside_legacy_namespace(rel: str, namespace: str) -> bool:
    root = LEGACY_NAMESPACE_PATHS[namespace]
    if not root.is_relative_to(ROOT):
        return False
    legacy_rel = root.relative_to(ROOT).as_posix()
    return rel == legacy_rel or rel.startswith(legacy_rel + "/")


def legacy_namespace_import_edges(files: list[Path]) -> list[dict[str, object]]:
    """Return one record per source/legacy-namespace import dependency."""
    records: list[dict[str, object]] = []
    for path in files:
        rel = _rel(path)
        references = import_references(path)
        for namespace in LEGACY_NAMESPACE_PATHS:
            matched = sorted(
                reference
                for reference in references
                if reference == namespace or reference.startswith(namespace + ".")
            )
            if not matched:
                continue
            records.append(
                {
                    "source": rel,
                    "legacy_namespace": namespace,
                    "references": matched,
                    "caller_class": _caller_class(rel),
                    "external": not _inside_legacy_namespace(rel, namespace),
                }
            )
    return records


def legacy_namespace_presence() -> list[str]:
    return sorted(
        namespace
        for namespace, path in LEGACY_NAMESPACE_PATHS.items()
        if path.is_dir()
    )


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
    bin_files = _python_files(ROOT / "bin")
    script_files = _python_files(ROOT / "scripts")
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
    legacy_edges = legacy_namespace_import_edges(_repository_python_files())
    external_legacy_edges = [record for record in legacy_edges if record["external"]]
    present_legacy_namespaces = legacy_namespace_presence()
    zero_legacy = not present_legacy_namespaces and not external_legacy_edges
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
        "legacy_namespaces_present": present_legacy_namespaces,
        "legacy_namespace_import_edges": legacy_edges,
        "external_legacy_import_edges": external_legacy_edges,
        "zero_legacy": zero_legacy,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx-architecture-census")
    parser.add_argument("--json-out")
    parser.add_argument(
        "--require-no-legacy",
        action="store_true",
        help="fail if a #143 legacy namespace or external caller still exists",
    )
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
    print(f"ISSUE143_LEGACY_NAMESPACES_PRESENT: {len(result['legacy_namespaces_present'])}")
    for namespace in result["legacy_namespaces_present"]:
        print(f"ISSUE143_LEGACY_NAMESPACE: {namespace}")
    print(f"ISSUE143_EXTERNAL_LEGACY_IMPORTS: {len(result['external_legacy_import_edges'])}")
    for edge in result["external_legacy_import_edges"]:
        print(
            "ISSUE143_LEGACY_IMPORT: "
            f"{edge['source']} -> {edge['legacy_namespace']} "
            f"[{edge['caller_class']}]"
        )
    print(f"ISSUE143_ZERO_LEGACY: {'PASS' if result['zero_legacy'] else 'FAIL'}")
    print(f"ISSUE70_ARCHITECTURE_CENSUS: {result['status']}")
    passed = result["status"] == "PASS"
    if args.require_no_legacy:
        passed = passed and bool(result["zero_legacy"])
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
