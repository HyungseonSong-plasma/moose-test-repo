#!/usr/bin/env python3
"""P0 characterization for Issue46 augmented-localization owner convergence."""
from __future__ import annotations

import ast
import importlib
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import electron_inventory_nullspace as inv
from qpx_harness.moose import dofmap as dm
from qpx_harness.petsc import matrix as pm
from recipes import issue45_first_linear as first_linear
from recipes import issue46_jacobian_localization as recipe

LEGACY_MODULE = "qpx_harness.augmented_jacobian_localization"
LEGACY = ROOT / "qpx_harness" / "augmented_jacobian_localization.py"
SEMANTIC = ROOT / "qpx_harness" / "issue46_jacobian_localization.py"
FD_AUDIT = ROOT / "qpx_harness" / "jacobian_fd_reference_audit.py"
CLI = ROOT / "scripts" / "qpx.py"

EXPECTED_PRODUCTION_CONSUMERS = {
    "qpx_harness/jacobian_fd_reference_audit.py",
    "scripts/qpx.py",
}
EXPECTED_TEST_CONSUMERS = {
    "tests/Issue47_fd_reference_refactor_characterization/self_test.py",
    "tests/Issue47_fd_reference_refactor_characterization/wp3b_provenance_characterization.py",
    "tests/Issue48_qpx_harness_generality/self_test.py",
    "tests/Issue48_qpx_harness_generality/wp2_matrix_characterization.py",
    "tests/Issue48_qpx_harness_generality/wp4_issue46_fd_recipe_characterization.py",
}
RUNTIME_POLICY_SURFACE = (
    "audit_localization_structure",
    "build_framework_control_input",
    "audit_framework_control_structure",
    "analyze_localization_text",
    "analyze_framework_control_runtime",
    "evaluate_runtime_batch",
    "self_test",
    "_prepare_cases",
    "run_preflight",
    "run_runtime",
    "main",
)
RECIPE_SURFACE = (
    "instrument_localization",
    "LOCALIZATION_THRESHOLD",
    "DOFMAP_OUTPUT",
    "DOFMAP_FILE_BASE",
)


def _legacy() -> Any:
    # Dynamic import observes the current owner without becoming a static
    # cleanup consumer itself.
    return importlib.import_module(LEGACY_MODULE)


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


def _consumer_sets() -> tuple[set[str], set[str]]:
    production: set[str] = set()
    tests: set[str] = set()
    for rel_root in ("qpx_harness", "recipes", "scripts", "tests", "performance"):
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


def _assert_equal(label: str, left: object, right: object) -> None:
    if left != right:
        raise AssertionError(f"{label} drift:\nleft={left!r}\nright={right!r}")


def _check_consumer_topology() -> None:
    production, tests = _consumer_sets()
    if production != EXPECTED_PRODUCTION_CONSUMERS:
        raise AssertionError(
            "augmented-localization production-consumer drift: "
            f"observed={sorted(production)} "
            f"expected={sorted(EXPECTED_PRODUCTION_CONSUMERS)}"
        )
    if tests != EXPECTED_TEST_CONSUMERS:
        raise AssertionError(
            "augmented-localization test-consumer drift: "
            f"observed={sorted(tests)} expected={sorted(EXPECTED_TEST_CONSUMERS)}"
        )


def _check_construction_owner_equivalence() -> None:
    legacy = _legacy()
    for name in ("TARGET", "LOCALIZATION_THRESHOLD", "DOFMAP_OUTPUT", "DOFMAP_FILE_BASE"):
        _assert_equal(name, getattr(recipe, name), getattr(legacy, name))

    base = inv._synthetic_constrained_input(recipe.TARGET)
    first_text, _ = first_linear.instrument_first_linear(base)
    legacy_text, legacy_meta = legacy.instrument_localization(first_text)
    recipe_text, recipe_meta = recipe.instrument_localization(first_text)
    _assert_equal("localization construction text", recipe_text, legacy_text)
    _assert_equal("localization construction metadata", recipe_meta, legacy_meta)

    recipe_source = Path(recipe.__file__).read_text()
    if "augmented_jacobian_localization" in recipe_source:
        raise AssertionError("Issue46 localization recipe reverse-depends on legacy owner")
    for token in (
        "def run_preflight(",
        "def run_runtime(",
        "def main(",
        "def analyze_localization_text(",
        "def audit_framework_control_structure(",
    ):
        if token in recipe_source:
            raise AssertionError(f"runtime/policy surface leaked into construction recipe: {token}")


def _check_generic_primitive_equivalence() -> None:
    legacy = _legacy()

    dofmap_text = legacy._synthetic_dof_map()
    legacy_dofmap = legacy.parse_dof_map_text(dofmap_text)
    generic_dofmap = dm.parse_dof_map_text(
        dofmap_text,
        expected_variables=legacy.MAIN_VARIABLES,
        scalar_variables=legacy.SCALAR_VARIABLES,
    )
    _assert_equal("DOF ownership", generic_dofmap, legacy_dofmap)

    log = legacy._synthetic_localization_log(
        [(0, 4, 2.0e-4), (4, 1, -3.0e-4)]
    )
    legacy_difference = legacy.parse_threshold_difference_matrix(log)
    generic_difference = pm.parse_threshold_difference_matrix(log)
    _assert_equal("threshold matrix facts", generic_difference, legacy_difference)

    legacy_localized = legacy.localize_difference_entries(
        legacy_difference, legacy_dofmap
    )
    generic_localized = pm.summarize_by_owner(
        generic_difference, generic_dofmap["owner_by_dof"]
    )
    for key in (
        "blocks",
        "unmapped_entries",
        "entry_count",
        "mapped_entry_count",
        "thresholded_l2_difference",
    ):
        _assert_equal(
            f"generic localization fact {key}",
            generic_localized[key],
            legacy_localized[key],
        )

    for path in (Path(dm.__file__), Path(pm.__file__)):
        source = path.read_text()
        if "augmented_jacobian_localization" in source or "recipes." in source:
            raise AssertionError(f"reverse dependency leaked into generic primitive: {path}")


def _check_runtime_policy_boundary() -> None:
    legacy = _legacy()
    if not LEGACY.is_file():
        raise AssertionError("current augmented-localization owner is missing")
    if SEMANTIC.exists():
        raise AssertionError(
            "semantic Issue46 localization runtime owner already exists; "
            "this pre-cutover characterization must be evolved"
        )
    for name in RECIPE_SURFACE:
        if not hasattr(recipe, name):
            raise AssertionError(f"canonical Issue46 construction surface missing: {name}")
    for name in RUNTIME_POLICY_SURFACE:
        obj = getattr(legacy, name, None)
        if not callable(obj):
            raise AssertionError(f"legacy runtime/policy surface missing: {name}")

    legacy_source = LEGACY.read_text()
    required_generic = (
        "from .petsc import options as petsc_options",
    )
    for token in required_generic:
        if token not in legacy_source:
            raise AssertionError(f"legacy owner lost existing generic composition: {token}")


def _check_consumer_role_boundary() -> None:
    fd_source = FD_AUDIT.read_text()
    if "from . import augmented_jacobian_localization as loc" not in fd_source:
        raise AssertionError("FD-reference consumer import shape drifted")
    loc_symbols = set(re.findall(r"\bloc\.([A-Za-z_][A-Za-z0-9_]*)", fd_source))
    if loc_symbols != {"LOCALIZATION_THRESHOLD"}:
        raise AssertionError(
            "FD-reference consumer depends on more than the recipe-owned threshold: "
            f"{sorted(loc_symbols)}"
        )
    if "from recipes import issue46_jacobian_localization" in fd_source:
        raise AssertionError("FD-reference consumer was cut over before characterization")

    cli_source = CLI.read_text()
    cli_import = (
        "from qpx_harness.augmented_jacobian_localization import main as "
        "jac_localization_main, self_test as jac_localization_self_test"
    )
    if cli_import not in cli_source:
        raise AssertionError("stable Issue46 localization CLI import surface drifted")
    if '"inventory-jacobian-localization":' not in cli_source:
        raise AssertionError("stable inventory-jacobian-localization command missing")


def _negative_control() -> None:
    source = "from qpx_harness import augmented_jacobian_localization as old\n"
    path = ROOT / "tests" / "synthetic_augmented_consumer.py"
    tree = ast.parse(source, filename=str(path))
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module == "qpx_harness" and any(
            alias.name == "augmented_jacobian_localization" for alias in node.names
        ):
            found = True
            break
    if not found:
        raise AssertionError("consumer-detection negative control failed")


def main() -> int:
    try:
        _check_consumer_topology()
        print("ISSUE48_WP23_AUGMENTED_OWNER_CHECK: consumer-topology=PASS")
        _check_construction_owner_equivalence()
        print(
            "ISSUE48_WP23_AUGMENTED_OWNER_CHECK: "
            "construction-owner-equivalence=PASS"
        )
        _check_generic_primitive_equivalence()
        print("ISSUE48_WP23_AUGMENTED_OWNER_CHECK: generic-primitive-equivalence=PASS")
        _check_runtime_policy_boundary()
        print("ISSUE48_WP23_AUGMENTED_OWNER_CHECK: runtime-policy-boundary=PASS")
        _check_consumer_role_boundary()
        print("ISSUE48_WP23_AUGMENTED_OWNER_CHECK: consumer-role-boundary=PASS")
        _negative_control()
        print("ISSUE48_WP23_AUGMENTED_OWNER_CHECK: negative-control=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP23_AUGMENTED_OWNER_CHARACTERIZATION: FAIL ({exc})")
        return 1

    print("ISSUE48_WP23_AUGMENTED_OWNER_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
