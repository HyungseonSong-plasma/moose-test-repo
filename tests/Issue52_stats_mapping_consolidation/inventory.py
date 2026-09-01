"""Branch-local AST inventory for Issue52 Stats mapping consolidation.

This checker is read-only with respect to repository source. It inventories the
canonical Stats builder surface, producer-local Stats bridge helpers, direct
SimulationStats construction, and import/call sites so later consolidation and
retirement cuts can use an explicit dependency graph instead of text grep.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("qpx_harness", "recipes", "scripts", "tests")
TARGET_BUILDERS = {
    "build_common_stats",
    "build_runtime_common_stats",
    "build_efficiency_stats",
    "build_convergence_stats",
    "build_accuracy_stats",
    "build_simulation_stats",
    "build_runtime_simulation_stats",
}


def _python_files() -> list[Path]:
    paths: list[Path] = []
    this_file = Path(__file__).resolve()
    for root_name in SCAN_ROOTS:
        root = ROOT / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if path.resolve() == this_file:
                continue
            paths.append(path)
    return sorted(paths)


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _function_loc(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    end = getattr(node, "end_lineno", None)
    if end is None:
        return 0
    return int(end) - int(node.lineno) + 1


def _looks_like_stats_bridge(name: str) -> bool:
    return name.startswith("build_") and name.endswith("_stats")


def inventory() -> dict[str, Any]:
    builder_callers: dict[str, list[dict[str, Any]]] = {
        name: [] for name in sorted(TARGET_BUILDERS)
    }
    stats_builder_importers: list[dict[str, Any]] = []
    bridge_helpers: list[dict[str, Any]] = []
    direct_simulation_stats: list[dict[str, Any]] = []
    parse_failures: list[dict[str, str]] = []

    for path in _python_files():
        rel = _relative(path)
        try:
            tree = ast.parse(path.read_text(), filename=rel)
        except (OSError, SyntaxError) as exc:
            parse_failures.append({"path": rel, "error": str(exc)})
            continue

        imported_builder_names: set[str] = set()
        simulation_stats_aliases: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.endswith("analysis.stats_builder") or module.endswith("stats_builder"):
                    names = []
                    for alias in node.names:
                        names.append(alias.name)
                        if alias.name in TARGET_BUILDERS:
                            imported_builder_names.add(alias.asname or alias.name)
                    stats_builder_importers.append(
                        {
                            "path": rel,
                            "line": node.lineno,
                            "module": "." * node.level + module,
                            "names": sorted(names),
                        }
                    )
                if module.endswith("models.stats"):
                    for alias in node.names:
                        if alias.name == "SimulationStats":
                            simulation_stats_aliases.add(alias.asname or alias.name)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _looks_like_stats_bridge(node.name) and rel != "qpx_harness/analysis/stats_builder.py":
                    bridge_helpers.append(
                        {
                            "path": rel,
                            "name": node.name,
                            "line": node.lineno,
                            "loc": _function_loc(node),
                        }
                    )

            if not isinstance(node, ast.Call):
                continue

            if isinstance(node.func, ast.Name):
                called = node.func.id
                for target in TARGET_BUILDERS:
                    if called == target:
                        builder_callers[target].append(
                            {"path": rel, "line": node.lineno, "form": "direct"}
                        )
                if called in simulation_stats_aliases or called == "SimulationStats":
                    direct_simulation_stats.append(
                        {"path": rel, "line": node.lineno, "form": "direct"}
                    )
            elif isinstance(node.func, ast.Attribute):
                called = node.func.attr
                if called in TARGET_BUILDERS:
                    builder_callers[called].append(
                        {"path": rel, "line": node.lineno, "form": "attribute"}
                    )
                if called == "SimulationStats":
                    direct_simulation_stats.append(
                        {"path": rel, "line": node.lineno, "form": "attribute"}
                    )

    for rows in builder_callers.values():
        rows.sort(key=lambda row: (row["path"], row["line"]))
    stats_builder_importers.sort(key=lambda row: (row["path"], row["line"]))
    bridge_helpers.sort(key=lambda row: (row["path"], row["line"]))
    direct_simulation_stats.sort(key=lambda row: (row["path"], row["line"]))

    return {
        "builder_callers": builder_callers,
        "stats_builder_importers": stats_builder_importers,
        "bridge_helpers": bridge_helpers,
        "bridge_helper_loc_total": sum(row["loc"] for row in bridge_helpers),
        "direct_simulation_stats": direct_simulation_stats,
        "parse_failures": parse_failures,
    }


def self_test() -> int:
    report = inventory()
    failures = report["parse_failures"]
    if failures:
        print("ISSUE52_STATS_INVENTORY: FAIL")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1

    builder_path = ROOT / "qpx_harness" / "analysis" / "stats_builder.py"
    if not builder_path.is_file():
        print("ISSUE52_STATS_INVENTORY: FAIL")
        print("missing qpx_harness/analysis/stats_builder.py")
        return 1

    print("ISSUE52_STATS_INVENTORY: PASS")
    print(f"ISSUE52_STATS_BRIDGE_HELPER_LOC_BASELINE: {report['bridge_helper_loc_total']}")
    print("ISSUE52_STATS_INVENTORY_JSON_BEGIN")
    print(json.dumps(report, indent=2, sort_keys=True))
    print("ISSUE52_STATS_INVENTORY_JSON_END")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
