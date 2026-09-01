"""Apply Issue53 D2 Convergence extraction with fail-closed structural checks.

This migrator is intentionally branch-local and one-shot. It avoids reconstructing
stats_builder.py through a full-file transcription payload: the current local file
is parsed, the exact contiguous Convergence owner functions are removed by AST
line ranges, and one compatibility re-export import is inserted.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "qpx_harness" / "analysis" / "stats_builder.py"
EXPECTED_BRANCH = "refactor/qpx-harness-generality"

CONVERGENCE_LOCAL = {
    "_termination_rows",
    "_true_residual_samples",
    "_variable_residual_samples",
    "_scaling_factor_rows",
    "build_convergence_stats",
}
EFFICIENCY_LOCAL = {
    "_perfgraph_timings",
    "_petsc_timings",
    "_memory_stats",
    "build_efficiency_stats",
}
CORE_REQUIRED = {
    "build_problem_stats",
    "build_environment_stats",
    "build_common_stats",
    "build_runtime_common_stats",
    "_error_from_mapping",
    "_matrix_blocks",
    "_matrix_entries",
    "build_accuracy_stats",
    "build_simulation_stats",
    "build_runtime_simulation_stats",
    "self_test",
}


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _top_functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _imported_from(tree: ast.Module, module: str, *, level: int = 1) -> set[str]:
    out: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level == level and node.module == module:
            out.update(alias.name for alias in node.names)
    return out


def _preflight() -> tuple[str, ast.Module, dict[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    branch = _run("git", "rev-parse", "--abbrev-ref", "HEAD")
    if branch.returncode != 0 or branch.stdout.strip() != EXPECTED_BRANCH:
        raise AssertionError(
            f"wrong branch: expected {EXPECTED_BRANCH!r}, got {branch.stdout.strip()!r}"
        )

    dirty = _run("git", "status", "--porcelain", "--", str(TARGET.relative_to(ROOT)))
    if dirty.returncode != 0:
        raise AssertionError(dirty.stderr.strip() or "git status failed")
    if dirty.stdout.strip():
        raise AssertionError("stats_builder.py has local changes; refusing destructive migration")

    text = TARGET.read_text()
    tree = ast.parse(text, filename=TARGET.relative_to(ROOT).as_posix())
    functions = _top_functions(tree)
    local_names = set(functions)
    convergence_imported = "build_convergence_stats" in _imported_from(
        tree, "metrics.convergence"
    )

    present_convergence = CONVERGENCE_LOCAL & local_names
    if not present_convergence and convergence_imported:
        raise AssertionError("D2 already appears applied")

    missing_convergence = CONVERGENCE_LOCAL - local_names
    if missing_convergence:
        raise AssertionError(
            f"D1 topology mismatch; Convergence locals missing: {sorted(missing_convergence)}"
        )

    leaked_efficiency = EFFICIENCY_LOCAL & local_names
    if leaked_efficiency:
        raise AssertionError(
            f"D1 not complete; Efficiency implementation still local: {sorted(leaked_efficiency)}"
        )
    if "build_efficiency_stats" not in _imported_from(tree, "metrics.efficiency"):
        raise AssertionError("D1 Efficiency facade re-export missing")
    if convergence_imported:
        raise AssertionError("Convergence facade import already present before D2")

    missing_core = CORE_REQUIRED - local_names
    if missing_core:
        raise AssertionError(f"required core functions missing before D2: {sorted(missing_core)}")

    return text, tree, functions


def _build_intended(
    text: str,
    tree: ast.Module,
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
) -> str:
    nodes = [functions[name] for name in CONVERGENCE_LOCAL]
    start = min(node.lineno for node in nodes)
    end = max(int(node.end_lineno or node.lineno) for node in nodes)

    unexpected_top_level = []
    for node in tree.body:
        line = getattr(node, "lineno", -1)
        if start <= line <= end:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                unexpected_top_level.append(type(node).__name__)
            elif node.name not in CONVERGENCE_LOCAL:
                unexpected_top_level.append(node.name)
    if unexpected_top_level:
        raise AssertionError(
            f"unexpected top-level nodes inside D2 removal span: {unexpected_top_level}"
        )

    lines = text.splitlines(keepends=True)
    kept = lines[: start - 1] + lines[end:]
    intended = "".join(kept)

    anchor = "from .metrics.efficiency import build_efficiency_stats\n"
    addition = anchor + "from .metrics.convergence import build_convergence_stats\n"
    if intended.count(anchor) != 1:
        raise AssertionError("Efficiency import anchor is not unique")
    intended = intended.replace(anchor, addition, 1)

    parsed = ast.parse(intended, filename=TARGET.relative_to(ROOT).as_posix())
    after_functions = _top_functions(parsed)

    leaked_convergence = CONVERGENCE_LOCAL & set(after_functions)
    if leaked_convergence:
        raise AssertionError(
            f"Convergence implementation still local after intended D2: {sorted(leaked_convergence)}"
        )
    missing_core = CORE_REQUIRED - set(after_functions)
    if missing_core:
        raise AssertionError(
            f"D2 would remove unrelated core functions: {sorted(missing_core)}"
        )
    if "build_convergence_stats" not in _imported_from(parsed, "metrics.convergence"):
        raise AssertionError("D2 intended state lacks Convergence facade re-export")
    if "build_efficiency_stats" not in _imported_from(parsed, "metrics.efficiency"):
        raise AssertionError("D2 intended state lost Efficiency facade re-export")

    removed = len(text.splitlines()) - len(intended.splitlines())
    if removed < 150 or removed > 220:
        raise AssertionError(f"unexpected D2 LOC delta: {removed}")
    return intended


def _apply_atomically(original: str, intended: str) -> None:
    temp = TARGET.with_name(TARGET.name + ".issue53_d2.tmp")
    if temp.exists():
        raise AssertionError(f"stale migration temp file exists: {temp.name}")

    try:
        temp.write_text(intended)
        candidate = temp.read_text()
        parsed = ast.parse(candidate, filename=TARGET.relative_to(ROOT).as_posix())
        if CONVERGENCE_LOCAL & set(_top_functions(parsed)):
            raise AssertionError("temporary D2 candidate still contains Convergence locals")

        temp.replace(TARGET)
        reparsed = ast.parse(TARGET.read_text(), filename=TARGET.relative_to(ROOT).as_posix())
        if CONVERGENCE_LOCAL & set(_top_functions(reparsed)):
            raise AssertionError("post-replace Convergence locals remain")
        if "build_convergence_stats" not in _imported_from(
            reparsed, "metrics.convergence"
        ):
            raise AssertionError("post-replace Convergence facade re-export missing")
    except Exception:
        if temp.exists():
            temp.unlink()
        if TARGET.read_text() != original:
            TARGET.write_text(original)
        raise
    finally:
        if temp.exists():
            temp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    try:
        text, tree, functions = _preflight()
        intended = _build_intended(text, tree, functions)
        before = len(text.splitlines())
        after = len(intended.splitlines())
        print("ISSUE53_D2_MIGRATOR_PREFLIGHT: PASS")
        print(f"ISSUE53_D2_MIGRATOR_BEFORE_LOC: {before}")
        print(f"ISSUE53_D2_MIGRATOR_AFTER_LOC: {after}")
        print(f"ISSUE53_D2_MIGRATOR_REMOVED_LOC: {before - after}")

        if not args.apply:
            print("ISSUE53_D2_MIGRATOR_MODE: CHECK_ONLY")
            return 0

        _apply_atomically(text, intended)
        print("ISSUE53_D2_MIGRATOR_APPLY: PASS")
        return 0
    except Exception as exc:
        print(f"ISSUE53_D2_MIGRATOR: FAIL ({exc})")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
