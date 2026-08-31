#!/usr/bin/env python3
"""P0 characterization for Issue45 first-linear semantic-owner convergence."""
from __future__ import annotations

import ast
import importlib
import importlib.util
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import electron_inventory_nullspace as inv
from qpx_harness.petsc import options as po
from recipes import issue45_first_linear as recipe

LEGACY = ROOT / "qpx_harness" / "petsc_first_linear_diagnostic.py"
AUGMENTED = ROOT / "qpx_harness" / "augmented_jacobian_localization.py"
FD_AUDIT = ROOT / "qpx_harness" / "jacobian_fd_reference_audit.py"
CLI = ROOT / "scripts" / "qpx.py"
LEGACY_MODULE = "qpx_harness.petsc_first_linear_diagnostic"

EXPECTED_PRODUCTION_CONSUMERS = {
    "qpx_harness/augmented_jacobian_localization.py",
    "qpx_harness/jacobian_fd_reference_audit.py",
    "scripts/qpx.py",
}
EXPECTED_TEST_CONSUMERS = {
    "tests/Issue47_fd_reference_refactor_characterization/self_test.py",
    "tests/Issue48_qpx_harness_generality/self_test.py",
    "tests/Issue48_qpx_harness_generality/wp2_analysis_characterization.py",
    "tests/Issue48_qpx_harness_generality/wp4_issue45_first_linear_characterization.py",
    "tests/Issue48_qpx_harness_generality/wp4_issue46_fd_recipe_characterization.py",
}
RUNTIME_ORCHESTRATION_SURFACE = (
    "def _prepare_case(",
    "def _run_p2(",
    "def _preflight(",
    "def _write_summary(",
    "def run_preflight(",
    "def run_diagnostic(",
    "def self_test(",
    "def main(",
)
RECIPE_POLICY_SURFACE = (
    "def instrument_first_linear(",
    "def analyze_first_linear_text(",
)
ISSUE46_LEGACY_DEPENDENCIES = (
    "first_linear.JACOBIAN_REL_TOL",
    "first_linear.instrument_first_linear(",
    "first_linear._petsc_options(",
)
ISSUE46_FORBIDDEN_RUNTIME_DEPENDENCIES = (
    "first_linear.analyze_first_linear_text(",
    "first_linear.run_preflight(",
    "first_linear.run_diagnostic(",
    "first_linear.main(",
    "first_linear.self_test(",
)


def _legacy() -> Any:
    # Dynamic import is intentional: this characterization observes the legacy
    # owner without becoming a static cleanup consumer itself.
    return importlib.import_module(LEGACY_MODULE)


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
            if base == "qpx_harness" and any(
                f"qpx_harness.{alias.name}" == module_name for alias in node.names
            ):
                return True
    return False


def _consumer_sets() -> tuple[set[str], set[str]]:
    production: set[str] = set()
    tests: set[str] = set()
    for rel_root in ("qpx_harness", "recipes", "scripts", "tests"):
        base = ROOT / rel_root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if path == LEGACY:
                continue
            try:
                consumes = _imports_module(path, LEGACY_MODULE)
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


def _check_consumer_topology() -> None:
    production, tests = _consumer_sets()
    if production != EXPECTED_PRODUCTION_CONSUMERS:
        raise AssertionError(
            "first-linear production-consumer drift: "
            f"observed={sorted(production)} expected={sorted(EXPECTED_PRODUCTION_CONSUMERS)}"
        )
    if tests != EXPECTED_TEST_CONSUMERS:
        raise AssertionError(
            "first-linear test-consumer drift: "
            f"observed={sorted(tests)} expected={sorted(EXPECTED_TEST_CONSUMERS)}"
        )


def _check_policy_equivalence() -> None:
    legacy = _legacy()
    for name in (
        "TARGET",
        "DIAGNOSTIC_NL_MAX_ITS",
        "JACOBIAN_REL_TOL",
        "FIRST_LINEAR_PETSC_OPTIONS",
        "REQUIRED_EXISTING_OPTIONS",
    ):
        _assert_equivalent(name, getattr(recipe, name), getattr(legacy, name))

    base = inv._synthetic_constrained_input(recipe.TARGET)
    new_text, new_meta = recipe.instrument_first_linear(base)
    old_text, old_meta = legacy.instrument_first_linear(base)
    _assert_equivalent("construction-text", new_text, old_text)
    _assert_equivalent("construction-meta", new_meta, old_meta)

    for label, text in (("base", base), ("instrumented", old_text)):
        _assert_equivalent(
            f"petsc-flags:{label}",
            po.get_flags(text),
            legacy._petsc_options(text),
        )

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
        old = legacy.analyze_first_linear_text(text, returncode=1)
        new = recipe.analyze_first_linear_text(text, returncode=1)
        _assert_equivalent(f"analysis:{label}", new, old)


def _check_owner_boundary() -> None:
    source = LEGACY.read_text()
    recipe_source = Path(recipe.__file__).read_text()
    options_source = Path(po.__file__).read_text()

    for token in RUNTIME_ORCHESTRATION_SURFACE:
        if token not in source:
            raise AssertionError(f"legacy runtime surface drift: {token}")
    for token in RECIPE_POLICY_SURFACE:
        if token not in recipe_source:
            raise AssertionError(f"recipe policy surface missing: {token}")
    if "def get_flags(" not in options_source:
        raise AssertionError("generic PETSc flag reader missing from canonical primitive owner")

    if "petsc_first_linear_diagnostic" in recipe_source:
        raise AssertionError("Issue45 recipe reverse-depends on legacy first-linear owner")
    if "petsc_first_linear_diagnostic" in options_source:
        raise AssertionError("generic PETSc option primitive reverse-depends on legacy owner")
    for token in (
        "def _prepare_case(",
        "def _run_p2(",
        "def _preflight(",
        "def run_diagnostic(",
        "def main(",
    ):
        if token in recipe_source:
            raise AssertionError(f"runtime orchestration leaked into recipe: {token}")


def _check_production_contracts() -> None:
    augmented = AUGMENTED.read_text()
    fd_audit = FD_AUDIT.read_text()
    cli = CLI.read_text()

    for path, source in ((AUGMENTED, augmented), (FD_AUDIT, fd_audit)):
        if "from . import petsc_first_linear_diagnostic as first_linear" not in source:
            raise AssertionError(f"unexpected first-linear import shape: {path}")
        missing = [token for token in ISSUE46_LEGACY_DEPENDENCIES if token not in source]
        if missing:
            raise AssertionError(
                f"Issue46 legacy dependency surface drift: {path}: missing={missing}"
            )
        leaked_runtime = [
            token for token in ISSUE46_FORBIDDEN_RUNTIME_DEPENDENCIES if token in source
        ]
        if leaked_runtime:
            raise AssertionError(
                f"Issue46 consumer depends on first-linear runtime orchestration: "
                f"{path}: {leaked_runtime}"
            )

    # Every current Issue46 dependency has a pre-existing canonical destination.
    legacy = _legacy()
    if recipe.JACOBIAN_REL_TOL != legacy.JACOBIAN_REL_TOL:
        raise AssertionError("canonical recipe Jacobian tolerance drifted from legacy owner")
    if not callable(recipe.instrument_first_linear):
        raise AssertionError("canonical recipe first-linear instrumentation is unavailable")
    if not callable(po.get_flags):
        raise AssertionError("canonical generic PETSc flag reader is unavailable")

    cli_import = (
        "from qpx_harness.petsc_first_linear_diagnostic import main as "
        "first_linear_main, self_test as first_linear_self_test"
    )
    if cli_import not in cli:
        raise AssertionError("stable inventory-first-linear CLI import shape drifted")
    if '"inventory-first-linear":' not in cli:
        raise AssertionError("stable inventory-first-linear command missing")


def _negative_control() -> None:
    source = "from qpx_harness import petsc_first_linear_diagnostic as first_linear\n"
    path = ROOT / "qpx_harness" / "synthetic_consumer.py"
    tree = ast.parse(source, filename=str(path))
    if not any(isinstance(node, ast.ImportFrom) for node in ast.walk(tree)):
        raise AssertionError("consumer-detection negative control is invalid")
    package = ".".join(path.relative_to(ROOT).with_suffix("").parts[:-1])
    if package != "qpx_harness":
        raise AssertionError("synthetic consumer package control drifted")


def main() -> int:
    try:
        _check_consumer_topology()
        print("ISSUE48_WP20_FIRST_LINEAR_OWNER_CHECK: consumer-topology=PASS")
        _check_policy_equivalence()
        print("ISSUE48_WP20_FIRST_LINEAR_OWNER_CHECK: canonical-destination-equivalence=PASS")
        _check_owner_boundary()
        print("ISSUE48_WP20_FIRST_LINEAR_OWNER_CHECK: runtime-policy-boundary=PASS")
        _check_production_contracts()
        print("ISSUE48_WP20_FIRST_LINEAR_OWNER_CHECK: production-contracts=PASS")
        _negative_control()
        print("ISSUE48_WP20_FIRST_LINEAR_OWNER_CHECK: negative-control=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP20_FIRST_LINEAR_OWNER_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP20_FIRST_LINEAR_OWNER_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
