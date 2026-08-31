#!/usr/bin/env python3
"""P0 post-retirement characterization for the Issue45 first-linear semantic owner."""
from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recipes import issue45_first_linear as recipe

LEGACY = ROOT / "qpx_harness" / "petsc_first_linear_diagnostic.py"
LEGACY_MODULE = "qpx_harness.petsc_first_linear_diagnostic"
SEMANTIC_MODULE = "qpx_harness.issue45_first_linear"
SEMANTIC = ROOT / "qpx_harness" / "issue45_first_linear.py"
CLI = ROOT / "scripts" / "qpx.py"

RUNTIME_SURFACE = (
    "_prepare_case",
    "_run_p2",
    "_preflight",
    "_write_summary",
    "run_preflight",
    "run_diagnostic",
    "self_test",
    "main",
)
POLICY_CONSTANTS = (
    "ISSUE",
    "TARGET",
    "DIAGNOSTIC_NL_MAX_ITS",
    "JACOBIAN_REL_TOL",
    "FIRST_LINEAR_PETSC_OPTIONS",
    "REQUIRED_EXISTING_OPTIONS",
)


def _semantic() -> Any:
    return importlib.import_module(SEMANTIC_MODULE)


def _imports_module(path: Path, module_name: str) -> bool:
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == module_name for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                try:
                    base = importlib.util.resolve_name(
                        "." * node.level + (node.module or ""), package
                    )
                except (ImportError, ValueError):
                    continue
            else:
                base = node.module or ""
            if base == module_name:
                return True
            parent, _, child = module_name.rpartition(".")
            if base == parent and any(alias.name == child for alias in node.names):
                return True
    return False


def _check_topology() -> None:
    if LEGACY.exists():
        raise AssertionError("retired historical first-linear owner still exists")
    if not SEMANTIC.is_file():
        raise AssertionError("semantic Issue45 first-linear owner missing")
    cli = CLI.read_text()
    required = (
        "from qpx_harness.issue45_first_linear import main as "
        "first_linear_main, self_test as first_linear_self_test"
    )
    if required not in cli:
        raise AssertionError("stable CLI is not bound to semantic first-linear owner")
    if _imports_module(CLI, LEGACY_MODULE):
        raise AssertionError("stable CLI imports retired historical owner")


def _check_policy_identity() -> None:
    semantic = _semantic()
    for name in POLICY_CONSTANTS:
        if getattr(semantic, name) != getattr(recipe, name):
            raise AssertionError(f"semantic/recipe policy identity drift: {name}")
    if semantic.instrument_first_linear is not recipe.instrument_first_linear:
        raise AssertionError("semantic owner does not alias recipe instrumentation")
    if semantic.analyze_first_linear_text is not recipe.analyze_first_linear_text:
        raise AssertionError("semantic owner does not alias recipe analysis")


def _check_semantic_self_test() -> None:
    semantic = _semantic()
    if semantic.self_test() != 0:
        raise AssertionError("semantic Issue45 first-linear self-test failed")


def _check_runtime_surface() -> None:
    semantic = _semantic()
    source = SEMANTIC.read_text()
    if "from recipes import issue45_first_linear as first_linear_recipe" not in source:
        raise AssertionError("semantic owner does not compose canonical Issue45 recipe")
    if _imports_module(SEMANTIC, LEGACY_MODULE):
        raise AssertionError("semantic owner imports retired historical owner")
    for forbidden in (
        "def instrument_first_linear(",
        "def analyze_first_linear_text(",
        "def _parse_true_residuals(",
        "def _parse_first_linear(",
        "def _parse_first_ksp_view(",
    ):
        if forbidden in source:
            raise AssertionError(f"policy/parser duplication leaked into semantic owner: {forbidden}")
    for name in RUNTIME_SURFACE:
        obj = getattr(semantic, name, None)
        if not callable(obj):
            raise AssertionError(f"semantic runtime surface missing: {name}")
        inspect.signature(obj)


def _negative_control() -> None:
    source = "from qpx_harness import issue45_first_linear as semantic\n"
    tree = ast.parse(source)
    if not any(isinstance(node, ast.ImportFrom) for node in ast.walk(tree)):
        raise AssertionError("semantic-consumer negative control invalid")


def main() -> int:
    try:
        _check_topology()
        print("ISSUE48_WP21_FIRST_LINEAR_SEMANTIC_CHECK: retired-owner-topology=PASS")
        _check_policy_identity()
        print("ISSUE48_WP21_FIRST_LINEAR_SEMANTIC_CHECK: recipe-policy-identity=PASS")
        _check_semantic_self_test()
        print("ISSUE48_WP21_FIRST_LINEAR_SEMANTIC_CHECK: semantic-self-test=PASS")
        _check_runtime_surface()
        print("ISSUE48_WP21_FIRST_LINEAR_SEMANTIC_CHECK: runtime-surface=PASS")
        _negative_control()
        print("ISSUE48_WP21_FIRST_LINEAR_SEMANTIC_CHECK: negative-control=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP21_FIRST_LINEAR_SEMANTIC_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP21_FIRST_LINEAR_SEMANTIC_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
