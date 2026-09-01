"""Branch-local AST inventory for Issue53 stats_builder decomposition."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "qpx_harness" / "analysis" / "stats_builder.py"
SCAN_ROOTS = ("qpx_harness", "recipes", "scripts", "tests")
PUBLIC_BUILDERS = {
    "build_problem_stats",
    "build_environment_stats",
    "build_common_stats",
    "build_runtime_common_stats",
    "build_efficiency_stats",
    "build_convergence_stats",
    "build_accuracy_stats",
    "build_simulation_stats",
    "build_runtime_simulation_stats",
    "self_test",
}
DESTINATIONS = {
    "build_problem_stats": "qpx_harness/analysis/common.py",
    "build_environment_stats": "qpx_harness/analysis/common.py",
    "build_common_stats": "qpx_harness/analysis/common.py",
    "build_runtime_common_stats": "qpx_harness/analysis/common.py",
    "build_efficiency_stats": "qpx_harness/analysis/metrics/efficiency.py",
    "build_convergence_stats": "qpx_harness/analysis/metrics/convergence.py",
    "build_accuracy_stats": "qpx_harness/analysis/metrics/accuracy.py",
    "build_simulation_stats": "qpx_harness/analysis/stats_builder.py",
    "build_runtime_simulation_stats": "qpx_harness/analysis/stats_builder.py",
    "self_test": "tests/Issue53_stats_builder_decomposition/stats_builder_characterization.py",
}


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _loc(node: ast.AST) -> int:
    end = getattr(node, "end_lineno", None)
    start = getattr(node, "lineno", None)
    if not isinstance(start, int) or not isinstance(end, int):
        return 0
    return end - start + 1


def _python_files() -> list[Path]:
    this_file = Path(__file__).resolve()
    out: list[Path] = []
    for root_name in SCAN_ROOTS:
        root = ROOT / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if path.resolve() != this_file:
                out.append(path)
    return sorted(out)


def inventory() -> dict[str, Any]:
    text = BUILDER.read_text()
    tree = ast.parse(text, filename=_rel(BUILDER))
    builder_functions: list[dict[str, Any]] = []
    top_level_names: set[str] = set()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_level_names.add(node.name)
            calls = sorted(
                {
                    child.func.id
                    for child in ast.walk(node)
                    if isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Name)
                }
            )
            builder_functions.append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "loc": _loc(node),
                    "visibility": "public" if not node.name.startswith("_") else "private",
                    "destination": DESTINATIONS.get(node.name, "private-with-semantic-owner"),
                    "internal_calls": [name for name in calls if name in top_level_names or name in PUBLIC_BUILDERS],
                }
            )

    external_importers: dict[str, list[dict[str, Any]]] = {
        name: [] for name in sorted(PUBLIC_BUILDERS)
    }
    external_callers: dict[str, list[dict[str, Any]]] = {
        name: [] for name in sorted(PUBLIC_BUILDERS)
    }
    parse_failures: list[dict[str, str]] = []

    for path in _python_files():
        rel = _rel(path)
        if path == BUILDER:
            continue
        try:
            other = ast.parse(path.read_text(), filename=rel)
        except (OSError, SyntaxError) as exc:
            parse_failures.append({"path": rel, "error": str(exc)})
            continue
        for node in ast.walk(other):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.endswith("analysis.stats_builder") or module.endswith("stats_builder"):
                    for alias in node.names:
                        if alias.name in external_importers:
                            external_importers[alias.name].append(
                                {
                                    "path": rel,
                                    "line": node.lineno,
                                    "module": "." * node.level + module,
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
                if called in external_callers:
                    external_callers[called].append(
                        {"path": rel, "line": node.lineno, "form": form}
                    )

    for rows in external_importers.values():
        rows.sort(key=lambda row: (row["path"], row["line"]))
    for rows in external_callers.values():
        rows.sort(key=lambda row: (row["path"], row["line"]))

    owner_state: list[dict[str, Any]] = []
    for rel in (
        "qpx_harness/analysis/metrics/accuracy.py",
        "qpx_harness/analysis/metrics/convergence.py",
        "qpx_harness/analysis/metrics/efficiency.py",
    ):
        path = ROOT / rel
        owner_state.append(
            {
                "path": rel,
                "exists": path.is_file(),
                "loc": len(path.read_text().splitlines()) if path.is_file() else 0,
            }
        )

    self_test = next((row for row in builder_functions if row["name"] == "self_test"), None)
    return {
        "stats_builder_path": _rel(BUILDER),
        "stats_builder_loc": len(text.splitlines()),
        "functions": builder_functions,
        "self_test_loc": self_test["loc"] if self_test else 0,
        "external_importers": external_importers,
        "external_callers": external_callers,
        "metrics_owner_state": owner_state,
        "parse_failures": parse_failures,
    }


def self_test() -> int:
    try:
        report = inventory()
        if report["parse_failures"]:
            raise AssertionError("repository Python parse failures detected")
        if report["stats_builder_loc"] < 700:
            raise AssertionError("stats_builder baseline unexpectedly small")
        if not any(row["name"] == "build_efficiency_stats" for row in report["functions"]):
            raise AssertionError("build_efficiency_stats missing from baseline")
        if not any(row["name"] == "build_convergence_stats" for row in report["functions"]):
            raise AssertionError("build_convergence_stats missing from baseline")
        if not any(row["name"] == "build_accuracy_stats" for row in report["functions"]):
            raise AssertionError("build_accuracy_stats missing from baseline")
    except Exception as exc:
        print(f"ISSUE53_DECOMPOSITION_INVENTORY: FAIL ({exc})")
        return 1

    print("ISSUE53_DECOMPOSITION_INVENTORY: PASS")
    print(f"ISSUE53_STATS_BUILDER_LOC: {report['stats_builder_loc']}")
    print(f"ISSUE53_STATS_BUILDER_SELFTEST_LOC: {report['self_test_loc']}")
    print("ISSUE53_DECOMPOSITION_JSON_BEGIN")
    print(json.dumps(report, indent=2, sort_keys=True))
    print("ISSUE53_DECOMPOSITION_JSON_END")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
