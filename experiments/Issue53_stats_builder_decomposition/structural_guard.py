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
COMMON_LOCAL = COMMON_PUBLIC | {
    "_mapping",
    "_optional_float",
    "_optional_int",
    "_string_tuple",
    "_runtime_return_code",
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
COMPOSITION_BUILDERS = {
    "build_simulation_stats",
    "build_runtime_simulation_stats",
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


def _require_metric_facades(tree: ast.Module) -> None:
    required = {
        "metrics.efficiency": "build_efficiency_stats",
        "metrics.convergence": "build_convergence_stats",
        "metrics.accuracy": "build_accuracy_stats",
    }
    for module, symbol in required.items():
        if symbol not in _imported_names(tree, module):
            raise AssertionError(f"stats_builder does not re-export {module}.{symbol}")


def check(stage: str) -> None:
    text = TARGET.read_text()
    tree = ast.parse(text, filename=TARGET.relative_to(ROOT).as_posix())
    functions = _top_level_functions(tree)

    leaked_efficiency = EFFICIENCY_LOCAL & functions
    if leaked_efficiency:
        raise AssertionError(
            "Efficiency implementation still local after destructive extraction: "
            f"{sorted(leaked_efficiency)}"
        )
    if "build_efficiency_stats" not in _imported_names(tree, "metrics.efficiency"):
        raise AssertionError(
            "stats_builder does not re-export metrics.efficiency.build_efficiency_stats"
        )

    if stage == "d1":
        missing_core = (COMMON_PUBLIC | ACCURACY_LOCAL | COMPOSITION_BUILDERS | {"self_test"}) - functions
        if missing_core:
            raise AssertionError(f"unexpected core symbol removal: {sorted(missing_core)}")
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
            f"Convergence implementation still local after {stage.upper()}: "
            f"{sorted(leaked_convergence)}"
        )
    if "build_convergence_stats" not in _imported_names(tree, "metrics.convergence"):
        raise AssertionError(
            "stats_builder does not re-export metrics.convergence.build_convergence_stats"
        )

    if stage == "d2":
        missing_core = (COMMON_PUBLIC | ACCURACY_LOCAL | COMPOSITION_BUILDERS | {"self_test"}) - functions
        if missing_core:
            raise AssertionError(f"unexpected core symbol removal: {sorted(missing_core)}")
        if len(text.splitlines()) >= 700:
            raise AssertionError("D2 did not materially reduce stats_builder LOC")
        return

    leaked_accuracy = ACCURACY_LOCAL & functions
    if leaked_accuracy:
        raise AssertionError(
            f"Accuracy implementation still local after {stage.upper()}: {sorted(leaked_accuracy)}"
        )
    if "build_accuracy_stats" not in _imported_names(tree, "metrics.accuracy"):
        raise AssertionError(
            "stats_builder does not re-export metrics.accuracy.build_accuracy_stats"
        )

    if stage == "d3":
        missing_core = (COMMON_PUBLIC | COMPOSITION_BUILDERS | {"self_test"}) - functions
        if missing_core:
            raise AssertionError(f"unexpected core symbol removal: {sorted(missing_core)}")
        if len(text.splitlines()) >= 500:
            raise AssertionError("D3 did not materially reduce stats_builder LOC")
        return

    _require_metric_facades(tree)

    leaked_common = COMMON_LOCAL & functions
    if leaked_common:
        raise AssertionError(
            f"Common implementation still local after {stage.upper()}: {sorted(leaked_common)}"
        )
    common_exports = _imported_names(tree, "common")
    missing_common_exports = COMMON_PUBLIC - common_exports
    if missing_common_exports:
        raise AssertionError(
            "stats_builder does not re-export all Common owner symbols: "
            f"{sorted(missing_common_exports)}"
        )

    missing_composition = COMPOSITION_BUILDERS - functions
    if missing_composition:
        raise AssertionError(
            f"composition builders removed unexpectedly: {sorted(missing_composition)}"
        )

    if stage == "d4":
        if "self_test" not in functions:
            raise AssertionError("D4 moved self_test before its dedicated cut")
        if len(text.splitlines()) >= 300:
            raise AssertionError("D4 did not materially reduce stats_builder LOC")
        return

    if stage == "d5":
        if "self_test" in functions:
            raise AssertionError("embedded self_test still local after D5")
        if "self_test" not in _imported_names(tree, "stats_builder_characterization"):
            raise AssertionError(
                "stats_builder does not re-export stats_builder_characterization.self_test"
            )
        if len(text.splitlines()) >= 150:
            raise AssertionError("D5 did not reduce stats_builder to a thin facade")
        return

    raise AssertionError(f"unsupported stage: {stage}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        choices=("d1", "d2", "d3", "d4", "d5"),
        required=True,
    )
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
