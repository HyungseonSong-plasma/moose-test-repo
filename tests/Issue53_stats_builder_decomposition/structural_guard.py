"""Structural guard for destructive Issue53 stats_builder extraction cuts."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "qpx_harness" / "analysis" / "stats_builder.py"

COMMON_PUBLIC = {
    "build_problem_stats",
    "build_environment_stats",
    "build_common_stats",
    "build_runtime_common_stats",
}
CONVERGENCE_LOCAL = {
    "_termination_rows",
    "_true_residual_samples",
    "_variable_residual_samples",
    "_scaling_factor_rows",
    "build_convergence_stats",
}
ACCURACY_LOCAL = {
    "_error_from_mapping",
    "_matrix_blocks",
    "_matrix_entries",
    "build_accuracy_stats",
}
COMPOSITION = {
    "build_simulation_stats",
    "build_runtime_simulation_stats",
    "self_test",
}
EFFICIENCY_LOCAL = {
    "_perfgraph_timings",
    "_petsc_timings",
    "_memory_stats",
    "build_efficiency_stats",
}


def _top_level_functions(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _imported_names(tree: ast.Module, module: str, *, level: int = 1) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level != level or node.module != module:
            continue
        names.update(alias.name for alias in node.names)
    return names


def check(stage: str) -> None:
    text = TARGET.read_text()
    tree = ast.parse(text, filename=TARGET.relative_to(ROOT).as_posix())
    functions = _top_level_functions(tree)

    required_core = COMMON_PUBLIC | COMPOSITION
    if stage in {"d1", "d2"}:
        required_core |= ACCURACY_LOCAL
    missing_core = required_core - functions
    if missing_core:
        raise AssertionError(f"unexpected core symbol removal: {sorted(missing_core)}")

    leaked_efficiency = EFFICIENCY_LOCAL & functions
    if leaked_efficiency:
        raise AssertionError(
            f"Efficiency implementation still local after destructive extraction: {sorted(leaked_efficiency)}"
        )
    if "build_efficiency_stats" not in _imported_names(tree, "metrics.efficiency"):
        raise AssertionError("stats_builder does not re-export metrics.efficiency.build_efficiency_stats")

    if stage == "d1":
        missing_convergence = CONVERGENCE_LOCAL - functions
        if missing_convergence:
            raise AssertionError(
                f"D1 changed Convergence ownership unexpectedly: {sorted(missing_convergence)}"
            )
        if len(text.splitlines()) >= 900:
            raise AssertionError("D1 did not materially reduce stats_builder LOC")
        return

    leaked_convergence = CONVERGENCE_LOCAL & functions
    if leaked_convergence:
        raise AssertionError(
            f"Convergence implementation still local after {stage.upper()}: {sorted(leaked_convergence)}"
        )
    if "build_convergence_stats" not in _imported_names(tree, "metrics.convergence"):
        raise AssertionError(
            "stats_builder does not re-export metrics.convergence.build_convergence_stats"
        )

    if stage == "d2":
        if len(text.splitlines()) >= 700:
            raise AssertionError("D2 did not materially reduce stats_builder LOC")
        return

    if stage == "d3":
        leaked_accuracy = ACCURACY_LOCAL & functions
        if leaked_accuracy:
            raise AssertionError(
                f"Accuracy implementation still local after D3: {sorted(leaked_accuracy)}"
            )
        if "build_accuracy_stats" not in _imported_names(tree, "metrics.accuracy"):
            raise AssertionError(
                "stats_builder does not re-export metrics.accuracy.build_accuracy_stats"
            )
        if len(text.splitlines()) >= 500:
            raise AssertionError("D3 did not materially reduce stats_builder LOC")
        return

    raise AssertionError(f"unsupported stage: {stage}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("d1", "d2", "d3"), required=True)
    args = parser.parse_args()
    try:
        check(args.stage)
    except Exception as exc:
        print(f"ISSUE53_STRUCTURAL_GUARD_{args.stage.upper()}: FAIL ({exc})")
        return 1
    print(f"ISSUE53_STRUCTURAL_GUARD_{args.stage.upper()}: PASS")
    print(f"ISSUE53_STRUCTURAL_GUARD_LOC: {len(TARGET.read_text().splitlines())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
