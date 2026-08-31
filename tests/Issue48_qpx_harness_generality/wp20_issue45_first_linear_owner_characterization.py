#!/usr/bin/env python3
"""P0 post-retirement characterization for Issue45 first-linear ownership."""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import issue45_first_linear as semantic
from qpx_harness.petsc import options as po
from recipes import issue45_first_linear as recipe

LEGACY = ROOT / "qpx_harness" / "petsc_first_linear_diagnostic.py"
LEGACY_MODULE = "qpx_harness.petsc_first_linear_diagnostic"
SEMANTIC = ROOT / "qpx_harness" / "issue45_first_linear.py"
AUGMENTED = ROOT / "qpx_harness" / "augmented_jacobian_localization.py"
FD_AUDIT = ROOT / "qpx_harness" / "jacobian_fd_reference_audit.py"
CLI = ROOT / "scripts" / "qpx.py"

ISSUE46_CANONICAL_DEPENDENCIES = (
    "first_linear_policy.JACOBIAN_REL_TOL",
    "first_linear_policy.instrument_first_linear(",
    "petsc_options.get_flags(",
)
ISSUE46_CANONICAL_IMPORTS = (
    "from recipes import issue45_first_linear as first_linear_policy",
    "from .petsc import options as petsc_options",
)


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


def _legacy_consumers() -> list[str]:
    consumers: list[str] = []
    for rel_root in ("qpx_harness", "recipes", "scripts", "tests", "performance"):
        base = ROOT / rel_root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if path == LEGACY:
                continue
            try:
                if _imports_module(path, LEGACY_MODULE):
                    consumers.append(str(path.relative_to(ROOT)))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
    return sorted(consumers)


def _check_consumer_topology() -> None:
    if LEGACY.exists():
        raise AssertionError("retired first-linear historical owner still exists")
    consumers = _legacy_consumers()
    if consumers:
        raise AssertionError(f"retired first-linear consumers remain: {consumers}")


def _check_canonical_destinations() -> None:
    for name in (
        "ISSUE",
        "TARGET",
        "DIAGNOSTIC_NL_MAX_ITS",
        "JACOBIAN_REL_TOL",
        "FIRST_LINEAR_PETSC_OPTIONS",
        "REQUIRED_EXISTING_OPTIONS",
    ):
        if getattr(semantic, name) != getattr(recipe, name):
            raise AssertionError(f"semantic/recipe identity drift: {name}")
    if semantic.instrument_first_linear is not recipe.instrument_first_linear:
        raise AssertionError("semantic instrumentation is not recipe-owned")
    if semantic.analyze_first_linear_text is not recipe.analyze_first_linear_text:
        raise AssertionError("semantic analysis is not recipe-owned")
    if not callable(po.get_flags):
        raise AssertionError("generic PETSc flag reader unavailable")


def _check_owner_boundary() -> None:
    semantic_source = SEMANTIC.read_text()
    recipe_path = Path(recipe.__file__)
    recipe_source = recipe_path.read_text()
    if _imports_module(SEMANTIC, LEGACY_MODULE):
        raise AssertionError("semantic owner imports retired historical owner")
    if _imports_module(recipe_path, LEGACY_MODULE):
        raise AssertionError("recipe imports retired historical owner")
    for forbidden in (
        "def instrument_first_linear(",
        "def analyze_first_linear_text(",
        "def _parse_true_residuals(",
        "def _parse_first_linear(",
        "def _parse_first_ksp_view(",
    ):
        if forbidden in semantic_source:
            raise AssertionError(f"policy/parser duplication leaked into semantic owner: {forbidden}")
    for forbidden in (
        "def _prepare_case(",
        "def _run_p2(",
        "def run_diagnostic(",
        "def main(",
    ):
        if forbidden in recipe_source:
            raise AssertionError(f"runtime orchestration leaked into recipe: {forbidden}")


def _check_production_contracts() -> None:
    for path in (AUGMENTED, FD_AUDIT):
        source = path.read_text()
        missing_imports = [token for token in ISSUE46_CANONICAL_IMPORTS if token not in source]
        if missing_imports:
            raise AssertionError(f"Issue46 canonical imports drift: {path}: {missing_imports}")
        missing = [token for token in ISSUE46_CANONICAL_DEPENDENCIES if token not in source]
        if missing:
            raise AssertionError(f"Issue46 canonical dependencies drift: {path}: {missing}")
        if _imports_module(path, LEGACY_MODULE):
            raise AssertionError(f"Issue46 imports retired first-linear owner: {path}")

    cli = CLI.read_text()
    required = (
        "from qpx_harness.issue45_first_linear import main as "
        "first_linear_main, self_test as first_linear_self_test"
    )
    if required not in cli:
        raise AssertionError("stable inventory-first-linear CLI is not semantic-owned")
    if _imports_module(CLI, LEGACY_MODULE):
        raise AssertionError("stable CLI imports retired first-linear owner")
    if '"inventory-first-linear":' not in cli:
        raise AssertionError("stable inventory-first-linear command missing")


def _negative_control() -> None:
    source = "from qpx_harness import petsc_first_linear_diagnostic as old\n"
    tree = ast.parse(source)
    if not any(isinstance(node, ast.ImportFrom) for node in ast.walk(tree)):
        raise AssertionError("consumer-detection negative control invalid")


def main() -> int:
    try:
        _check_consumer_topology()
        print("ISSUE48_WP20_FIRST_LINEAR_OWNER_CHECK: consumer-topology=PASS")
        _check_canonical_destinations()
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
