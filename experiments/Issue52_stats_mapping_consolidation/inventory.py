"""Branch-local AST inventory for Issue52 Stats mapping consolidation.

This checker is read-only with respect to repository source. It separates
canonical Stats owners from producer-local bridge helpers, inventories direct
call/import sites, and reports retirement evidence so later structural cuts do
not confuse ownership consolidation with raw LOC movement.
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
PRODUCER_BRIDGE_OWNERSHIP = {
    "build_first_linear_stats": (
        "selects Issue45 KSP/termination/true-residual/variable-residual/scaling facts",
    ),
    "build_jacobian_localization_stats": (
        "selects Issue46 thresholded/localized matrix comparison facts",
    ),
    "build_measurement_stats": (
        "selects PF1 work counters as convergence facts before SimulationStats construction",
    ),
}
UNCLASSIFIED_OWNERSHIP = "UNCLASSIFIED_REQUIRES_REVIEW"


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


def _looks_like_stats_helper(name: str) -> bool:
    return name.startswith("build_") and name.endswith("_stats")


def _is_canonical_owner(path: str) -> bool:
    return path.startswith("qpx_harness/analysis/")


def inventory() -> dict[str, Any]:
    builder_callers: dict[str, list[dict[str, Any]]] = {
        name: [] for name in sorted(TARGET_BUILDERS)
    }
    stats_builder_importers: list[dict[str, Any]] = []
    producer_bridges: list[dict[str, Any]] = []
    canonical_helpers: list[dict[str, Any]] = []
    direct_simulation_stats: list[dict[str, Any]] = []
    parse_failures: list[dict[str, str]] = []
    trees: dict[str, ast.Module] = {}

    for path in _python_files():
        rel = _relative(path)
        try:
            trees[rel] = ast.parse(path.read_text(), filename=rel)
        except (OSError, SyntaxError) as exc:
            parse_failures.append({"path": rel, "error": str(exc)})

    for rel, tree in trees.items():
        simulation_stats_aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.endswith("analysis.stats_builder") or module.endswith("stats_builder"):
                    names = [alias.name for alias in node.names]
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

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not _looks_like_stats_helper(node.name):
                    continue
                if rel == "qpx_harness/analysis/stats_builder.py":
                    continue
                record = {
                    "path": rel,
                    "name": node.name,
                    "line": node.lineno,
                    "loc": _function_loc(node),
                }
                if _is_canonical_owner(rel):
                    canonical_helpers.append(record)
                else:
                    ownership = list(
                        PRODUCER_BRIDGE_OWNERSHIP.get(
                            node.name,
                            (UNCLASSIFIED_OWNERSHIP,),
                        )
                    )
                    producer_bridges.append({**record, "semantic_ownership": ownership})

            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                called = node.func.id
                if called in TARGET_BUILDERS:
                    builder_callers[called].append(
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

    bridge_names = {row["name"] for row in producer_bridges}
    bridge_callers: dict[str, list[dict[str, Any]]] = {
        name: [] for name in sorted(bridge_names)
    }
    bridge_importers: dict[str, list[dict[str, Any]]] = {
        name: [] for name in sorted(bridge_names)
    }

    for rel, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = "." * node.level + (node.module or "")
                for alias in node.names:
                    if alias.name in bridge_names:
                        bridge_importers[alias.name].append(
                            {
                                "path": rel,
                                "line": node.lineno,
                                "module": module,
                                "asname": alias.asname,
                            }
                        )
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called = node.func.id
                    form = "direct"
                elif isinstance(node.func, ast.Attribute):
                    called = node.func.attr
                    form = "attribute"
                else:
                    continue
                if called in bridge_names:
                    bridge_callers[called].append(
                        {"path": rel, "line": node.lineno, "form": form}
                    )

    for rows in builder_callers.values():
        rows.sort(key=lambda row: (row["path"], row["line"]))
    for rows in bridge_callers.values():
        rows.sort(key=lambda row: (row["path"], row["line"]))
    for rows in bridge_importers.values():
        rows.sort(key=lambda row: (row["path"], row["line"]))
    stats_builder_importers.sort(key=lambda row: (row["path"], row["line"]))
    producer_bridges.sort(key=lambda row: (row["path"], row["line"]))
    canonical_helpers.sort(key=lambda row: (row["path"], row["line"]))
    direct_simulation_stats.sort(key=lambda row: (row["path"], row["line"]))

    producer_accuracy_callers = [
        row
        for row in builder_callers["build_accuracy_stats"]
        if not _is_canonical_owner(row["path"])
    ]
    retirement_candidates: list[dict[str, Any]] = []
    for bridge in producer_bridges:
        ownership = bridge["semantic_ownership"]
        if ownership:
            continue
        name = bridge["name"]
        external_calls = [
            row for row in bridge_callers[name] if row["path"] != bridge["path"]
        ]
        if not external_calls and not bridge_importers[name]:
            retirement_candidates.append(bridge)

    return {
        "builder_callers": builder_callers,
        "stats_builder_importers": stats_builder_importers,
        "producer_bridges": producer_bridges,
        "producer_bridge_loc_total": sum(row["loc"] for row in producer_bridges),
        "canonical_helpers": canonical_helpers,
        "canonical_helper_loc_total": sum(row["loc"] for row in canonical_helpers),
        "bridge_callers": bridge_callers,
        "bridge_importers": bridge_importers,
        "producer_accuracy_callers": producer_accuracy_callers,
        "retirement_candidates": retirement_candidates,
        "direct_simulation_stats": direct_simulation_stats,
        "parse_failures": parse_failures,
    }


def self_test() -> int:
    report = inventory()
    failures = report["parse_failures"]
    unclassified = [
        row
        for row in report["producer_bridges"]
        if UNCLASSIFIED_OWNERSHIP in row["semantic_ownership"]
    ]
    if failures or unclassified:
        print("ISSUE52_STATS_INVENTORY: FAIL")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1

    builder_path = ROOT / "qpx_harness" / "analysis" / "stats_builder.py"
    if not builder_path.is_file():
        print("ISSUE52_STATS_INVENTORY: FAIL")
        print("missing qpx_harness/analysis/stats_builder.py")
        return 1

    if report["producer_accuracy_callers"]:
        print("ISSUE52_STATS_INVENTORY: FAIL")
        print("producer-local direct build_accuracy_stats callers remain")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1

    print("ISSUE52_STATS_INVENTORY: PASS")
    print(f"ISSUE52_STATS_PRODUCER_BRIDGE_LOC: {report['producer_bridge_loc_total']}")
    print(f"ISSUE52_STATS_CANONICAL_HELPER_LOC: {report['canonical_helper_loc_total']}")
    print(
        "ISSUE52_STATS_RETIREMENT_CANDIDATE_COUNT: "
        f"{len(report['retirement_candidates'])}"
    )
    print("ISSUE52_STATS_INVENTORY_JSON_BEGIN")
    print(json.dumps(report, indent=2, sort_keys=True))
    print("ISSUE52_STATS_INVENTORY_JSON_END")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
