#!/usr/bin/env python3
"""P0 dual-owner characterization for Issue45 first-linear semantic convergence."""
from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import electron_inventory_nullspace as inv
from recipes import issue45_first_linear as recipe

LEGACY_MODULE = "qpx_harness.petsc_first_linear_diagnostic"
SEMANTIC_MODULE = "qpx_harness.issue45_first_linear"
LEGACY = ROOT / "qpx_harness" / "petsc_first_linear_diagnostic.py"
SEMANTIC = ROOT / "qpx_harness" / "issue45_first_linear.py"

EXPECTED_LEGACY_PRODUCTION_CONSUMERS = {"scripts/qpx.py"}
EXPECTED_LEGACY_TEST_CONSUMERS = {
    "tests/Issue47_fd_reference_refactor_characterization/self_test.py",
    "tests/Issue48_qpx_harness_generality/self_test.py",
    "tests/Issue48_qpx_harness_generality/wp2_analysis_characterization.py",
    "tests/Issue48_qpx_harness_generality/wp4_issue45_first_linear_characterization.py",
    "tests/Issue48_qpx_harness_generality/wp4_issue46_fd_recipe_characterization.py",
}
EXPECTED_SEMANTIC_PRODUCTION_CONSUMERS: set[str] = set()
EXPECTED_SEMANTIC_TEST_CONSUMERS: set[str] = set()

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


def _module(name: str) -> Any:
    # Dynamic import observes owner behavior without adding a static cleanup consumer.
    return importlib.import_module(name)


def _imports_module(path: Path, module_name: str) -> bool:
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == module_name for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                package = ".".join(path.relative_to(ROOT).with_suffix("").parts[:-1])
                try:
                    base = importlib.util.resolve_name(
                        "." * node.level + (node.module or ""), package
                    )
                except (ImportError, ValueError):
                    continue
            if base == module_name:
                return True
            package_root, _, child = module_name.rpartition(".")
            if base == package_root and any(alias.name == child for alias in node.names):
                return True
    return False


def _consumer_sets(module_name: str, owner_path: Path) -> tuple[set[str], set[str]]:
    production: set[str] = set()
    tests: set[str] = set()
    for rel_root in ("qpx_harness", "recipes", "scripts", "tests"):
        base = ROOT / rel_root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if path == owner_path:
                continue
            try:
                consumes = _imports_module(path, module_name)
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            if not consumes:
                continue
            rel = str(path.relative_to(ROOT))
            (tests if rel.startswith("tests/") else production).add(rel)
    return production, tests


def _equivalent(left: object, right: object) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        if math.isnan(left) and math.isnan(right):
            return True
        return left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _equivalent(left[key], right[key]) for key in left
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _equivalent(a, b) for a, b in zip(left, right)
        )
    return left == right


def _assert_equivalent(label: str, left: object, right: object) -> None:
    if not _equivalent(left, right):
        raise AssertionError(f"{label} drift:\nleft={left!r}\nright={right!r}")


def _check_topology() -> None:
    if not LEGACY.is_file() or not SEMANTIC.is_file():
        raise AssertionError("dual-owner files are not both present")

    legacy_prod, legacy_tests = _consumer_sets(LEGACY_MODULE, LEGACY)
    semantic_prod, semantic_tests = _consumer_sets(SEMANTIC_MODULE, SEMANTIC)
    if legacy_prod != EXPECTED_LEGACY_PRODUCTION_CONSUMERS:
        raise AssertionError(
            f"legacy production consumers drift: {sorted(legacy_prod)}"
        )
    if legacy_tests != EXPECTED_LEGACY_TEST_CONSUMERS:
        raise AssertionError(f"legacy test consumers drift: {sorted(legacy_tests)}")
    if semantic_prod != EXPECTED_SEMANTIC_PRODUCTION_CONSUMERS:
        raise AssertionError(
            f"semantic production consumers drift: {sorted(semantic_prod)}"
        )
    if semantic_tests != EXPECTED_SEMANTIC_TEST_CONSUMERS:
        raise AssertionError(f"semantic test consumers drift: {sorted(semantic_tests)}")


def _check_policy_identity() -> None:
    legacy = _module(LEGACY_MODULE)
    semantic = _module(SEMANTIC_MODULE)

    for name in POLICY_CONSTANTS:
        _assert_equivalent(name, getattr(semantic, name), getattr(legacy, name))
        _assert_equivalent(f"recipe:{name}", getattr(semantic, name), getattr(recipe, name))

    if semantic.instrument_first_linear is not recipe.instrument_first_linear:
        raise AssertionError("semantic owner does not alias canonical recipe instrumentation")
    if semantic.analyze_first_linear_text is not recipe.analyze_first_linear_text:
        raise AssertionError("semantic owner does not alias canonical recipe analysis")

    base = inv._synthetic_constrained_input(recipe.TARGET)
    legacy_text, legacy_meta = legacy.instrument_first_linear(base)
    semantic_text, semantic_meta = semantic.instrument_first_linear(base)
    _assert_equivalent("construction-text", semantic_text, legacy_text)
    _assert_equivalent("construction-meta", semantic_meta, legacy_meta)

    cases = {
        "positive": legacy._synthetic_log(),
        "jacobian-mismatch": legacy._synthetic_log(1.0e-3),
        "pc-failure": legacy._synthetic_log().replace(
            "Linear solve did not converge due to DIVERGED_BREAKDOWN iterations 30",
            "Linear solve did not converge due to DIVERGED_PC_FAILED iterations 0\n"
            "PC failed due to FACTOR_NUMERIC_ZEROPIVOT",
            1,
        ),
        "nonfinite": legacy._synthetic_log().replace(
            "n_e:                  5.0e-16",
            "n_e:                  nan",
            1,
        ),
        "missing-ksp-view": legacy._synthetic_log().split("KSP Object:", 1)[0],
        "restart-misaligned": legacy._synthetic_log().replace(
            "DIVERGED_BREAKDOWN iterations 30",
            "DIVERGED_BREAKDOWN iterations 29",
            1,
        ),
        "linear-converged": legacy._synthetic_log().replace(
            "Linear solve did not converge due to DIVERGED_BREAKDOWN iterations 30",
            "Linear solve converged due to CONVERGED_RTOL iterations 17",
            1,
        ),
    }
    for label, text in cases.items():
        _assert_equivalent(
            f"analysis:{label}",
            semantic.analyze_first_linear_text(text, returncode=1),
            legacy.analyze_first_linear_text(text, returncode=1),
        )


def _check_structure_equivalence() -> None:
    legacy = _module(LEGACY_MODULE)
    semantic = _module(SEMANTIC_MODULE)
    base = inv._synthetic_constrained_input(recipe.TARGET)
    diagnostic, _ = recipe.instrument_first_linear(base)

    for label, text in (
        ("positive", diagnostic),
        (
            "physics-mutation",
            diagnostic.replace("boundary = outlet", "boundary = plasma_cover", 1),
        ),
        (
            "full-jacobian-view",
            diagnostic.replace(
                "-snes_test_jacobian ",
                "-snes_test_jacobian -snes_test_jacobian_view ",
                1,
            ),
        ),
    ):
        _assert_equivalent(
            f"structure:{label}",
            semantic.audit_first_linear_structure(base, text),
            legacy.audit_first_linear_structure(base, text),
        )


def _check_runtime_surface() -> None:
    legacy = _module(LEGACY_MODULE)
    semantic = _module(SEMANTIC_MODULE)
    semantic_source = SEMANTIC.read_text()

    if "from recipes import issue45_first_linear as first_linear_recipe" not in semantic_source:
        raise AssertionError("semantic owner does not compose canonical Issue45 recipe")
    if "from . import petsc_first_linear_diagnostic" in semantic_source:
        raise AssertionError("semantic owner reverse-imports legacy first-linear owner")
    for forbidden in (
        "def instrument_first_linear(",
        "def analyze_first_linear_text(",
        "def _parse_true_residuals(",
        "def _parse_first_linear(",
        "def _parse_first_ksp_view(",
    ):
        if forbidden in semantic_source:
            raise AssertionError(f"policy/parser duplication leaked into semantic owner: {forbidden}")

    for name in RUNTIME_SURFACE:
        legacy_obj = getattr(legacy, name)
        semantic_obj = getattr(semantic, name)
        if inspect.signature(semantic_obj) != inspect.signature(legacy_obj):
            raise AssertionError(
                f"runtime signature drift for {name}: "
                f"semantic={inspect.signature(semantic_obj)} legacy={inspect.signature(legacy_obj)}"
            )

    if semantic._synthetic_log() != legacy._synthetic_log():
        raise AssertionError("semantic self-test fixture drifted from legacy owner")


def _negative_control() -> None:
    source = "from qpx_harness import issue45_first_linear as semantic\n"
    tree = ast.parse(source)
    if not any(isinstance(node, ast.ImportFrom) for node in ast.walk(tree)):
        raise AssertionError("semantic-consumer negative control is invalid")


def main() -> int:
    try:
        _check_topology()
        print("ISSUE48_WP21_FIRST_LINEAR_SEMANTIC_CHECK: dual-owner-topology=PASS")
        _check_policy_identity()
        print("ISSUE48_WP21_FIRST_LINEAR_SEMANTIC_CHECK: recipe-policy-identity=PASS")
        _check_structure_equivalence()
        print("ISSUE48_WP21_FIRST_LINEAR_SEMANTIC_CHECK: structure-equivalence=PASS")
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
