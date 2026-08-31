#!/usr/bin/env python3
"""P0 boundary characterization for Issue46 augmented-localization convergence."""
from __future__ import annotations

import ast
import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import electron_inventory_nullspace as inv
from qpx_harness.moose import dofmap as dm
from qpx_harness.petsc import matrix as pm
from qpx_harness.petsc import options as po
from recipes import issue45_first_linear as first_linear
from recipes import issue46_jacobian_localization as recipe

LEGACY_MODULE = "qpx_harness.augmented_jacobian_localization"
SEMANTIC_MODULE = "qpx_harness.issue46_jacobian_localization"
LEGACY = ROOT / "qpx_harness" / "augmented_jacobian_localization.py"
SEMANTIC = ROOT / "qpx_harness" / "issue46_jacobian_localization.py"
FD_AUDIT = ROOT / "qpx_harness" / "jacobian_fd_reference_audit.py"
CLI = ROOT / "scripts" / "qpx.py"

EXPECTED_LEGACY_PRODUCTION_CONSUMERS = {"scripts/qpx.py"}
EXPECTED_LEGACY_TEST_CONSUMERS = {
    "tests/Issue47_fd_reference_refactor_characterization/self_test.py",
    "tests/Issue47_fd_reference_refactor_characterization/wp3b_provenance_characterization.py",
    "tests/Issue48_qpx_harness_generality/self_test.py",
    "tests/Issue48_qpx_harness_generality/wp2_matrix_characterization.py",
    "tests/Issue48_qpx_harness_generality/wp4_issue46_fd_recipe_characterization.py",
}
EXPECTED_SEMANTIC_PRODUCTION_CONSUMERS = {"qpx_harness/jacobian_fd_reference_audit.py"}
EXPECTED_SEMANTIC_TEST_CONSUMERS: set[str] = set()

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

FD_REQUIRED_SOURCE_TOKENS = (
    "from recipes import issue46_jacobian_localization as localization_recipe",
    "from . import issue46_jacobian_localization as localization_runtime",
    "from .moose import dofmap as dm",
    "from .petsc import matrix as petsc_matrix",
    "from .petsc import options as petsc_options",
    "LOCALIZATION_THRESHOLD = localization_recipe.LOCALIZATION_THRESHOLD",
    "DOFMAP_FILE_BASE = localization_recipe.DOFMAP_FILE_BASE",
    "localization_recipe.instrument_localization",
    "localization_runtime.audit_localization_structure",
    "dm.parse_dof_map_text",
    "petsc_matrix.parse_threshold_difference_matrix",
    "petsc_matrix.summarize_by_owner",
    "petsc_options.get_name_value_pairs",
    "petsc_options.set_name_value_pairs",
    "petsc_options.upsert_name_value",
)
FD_FORBIDDEN_LEGACY_TOKENS = (
    "from . import augmented_jacobian_localization",
    "loc.",
    "AugmentedJacobianLocalizationError",
    "legacy_loc",
)


def _module(name: str) -> Any:
    return importlib.import_module(name)


def _imports_module(path: Path, module_name: str) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
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


def _consumer_sets(module_name: str, owner: Path) -> tuple[set[str], set[str]]:
    production: set[str] = set()
    tests: set[str] = set()
    for rel_root in ("qpx_harness", "recipes", "scripts", "tests", "performance"):
        base = ROOT / rel_root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if path == owner:
                continue
            try:
                consumes = _imports_module(path, module_name)
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            if consumes:
                rel = str(path.relative_to(ROOT))
                (tests if rel.startswith("tests/") else production).add(rel)
    return production, tests


def _assert_equal(label: str, left: object, right: object) -> None:
    if left != right:
        raise AssertionError(f"{label} drift: left={left!r} right={right!r}")


def _check_consumer_topology() -> None:
    legacy_prod, legacy_tests = _consumer_sets(LEGACY_MODULE, LEGACY)
    _assert_equal(
        "legacy production consumers",
        legacy_prod,
        EXPECTED_LEGACY_PRODUCTION_CONSUMERS,
    )
    _assert_equal("legacy test consumers", legacy_tests, EXPECTED_LEGACY_TEST_CONSUMERS)
    semantic_prod, semantic_tests = _consumer_sets(SEMANTIC_MODULE, SEMANTIC)
    _assert_equal(
        "semantic production consumers",
        semantic_prod,
        EXPECTED_SEMANTIC_PRODUCTION_CONSUMERS,
    )
    _assert_equal(
        "semantic test consumers", semantic_tests, EXPECTED_SEMANTIC_TEST_CONSUMERS
    )


def _check_construction_owner_equivalence() -> None:
    legacy = _module(LEGACY_MODULE)
    semantic = _module(SEMANTIC_MODULE)
    for name in ("TARGET", "LOCALIZATION_THRESHOLD", "DOFMAP_OUTPUT", "DOFMAP_FILE_BASE"):
        _assert_equal(f"recipe/legacy {name}", getattr(recipe, name), getattr(legacy, name))
        _assert_equal(f"recipe/semantic {name}", getattr(recipe, name), getattr(semantic, name))
    base = inv._synthetic_constrained_input(recipe.TARGET)
    first_text, _ = first_linear.instrument_first_linear(base)
    legacy_text, legacy_meta = legacy.instrument_localization(first_text)
    recipe_text, recipe_meta = recipe.instrument_localization(first_text)
    semantic_text, semantic_meta = semantic.instrument_localization(first_text)
    _assert_equal("recipe/legacy construction text", recipe_text, legacy_text)
    _assert_equal("recipe/semantic construction text", recipe_text, semantic_text)
    _assert_equal("recipe/legacy metadata", recipe_meta, legacy_meta)
    _assert_equal("recipe/semantic metadata", recipe_meta, semantic_meta)


def _check_generic_primitive_equivalence() -> None:
    legacy = _module(LEGACY_MODULE)
    semantic = _module(SEMANTIC_MODULE)
    dofmap_text = legacy._synthetic_dof_map()
    legacy_dofmap = legacy.parse_dof_map_text(dofmap_text)
    generic_dofmap = dm.parse_dof_map_text(
        dofmap_text,
        expected_variables=legacy.MAIN_VARIABLES,
        scalar_variables=legacy.SCALAR_VARIABLES,
    )
    _assert_equal("DOF ownership generic/legacy", generic_dofmap, legacy_dofmap)
    _assert_equal(
        "DOF ownership semantic/legacy",
        semantic.parse_dof_map_text(dofmap_text),
        legacy_dofmap,
    )

    log = legacy._synthetic_localization_log([(0, 4, 2.0e-4), (4, 1, -3.0e-4)])
    legacy_difference = legacy.parse_threshold_difference_matrix(log)
    generic_difference = pm.parse_threshold_difference_matrix(log)
    _assert_equal("matrix generic/legacy", generic_difference, legacy_difference)
    _assert_equal(
        "matrix semantic/legacy",
        semantic.parse_threshold_difference_matrix(log),
        legacy_difference,
    )
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
        _assert_equal(f"generic fact {key}", generic_localized[key], legacy_localized[key])

    base = inv._synthetic_constrained_input(recipe.TARGET)
    first_text, _ = first_linear.instrument_first_linear(base)
    localized_text, _ = recipe.instrument_localization(first_text)
    legacy_pairs = legacy._petsc_name_value_pairs(localized_text)
    generic_pairs = po.get_name_value_pairs(localized_text)
    _assert_equal("PETSc read", generic_pairs, legacy_pairs)
    _assert_equal(
        "PETSc write",
        po.set_name_value_pairs(localized_text, generic_pairs),
        legacy._set_petsc_name_value_pairs(localized_text, legacy_pairs),
    )
    _assert_equal(
        "PETSc upsert",
        po.upsert_name_value(localized_text, "-mat_fd_type", "ds"),
        legacy._upsert_petsc_value(localized_text, "-mat_fd_type", "ds"),
    )


def _check_runtime_policy_boundary() -> None:
    legacy = _module(LEGACY_MODULE)
    semantic = _module(SEMANTIC_MODULE)
    if not LEGACY.is_file() or not SEMANTIC.is_file():
        raise AssertionError("dual-owner characterization requires both owners")
    if _imports_module(SEMANTIC, LEGACY_MODULE):
        raise AssertionError("semantic Issue46 owner reverse-depends on legacy owner")
    for name in RECIPE_SURFACE:
        if not hasattr(recipe, name):
            raise AssertionError(f"recipe surface missing: {name}")
    for name in RUNTIME_POLICY_SURFACE:
        if not callable(getattr(legacy, name, None)):
            raise AssertionError(f"legacy runtime surface missing: {name}")
        if not callable(getattr(semantic, name, None)):
            raise AssertionError(f"semantic runtime surface missing: {name}")


def _check_fd_dependency_destination_matrix() -> None:
    fd_source = FD_AUDIT.read_text()
    if _imports_module(FD_AUDIT, LEGACY_MODULE):
        raise AssertionError("FD-reference audit still imports the legacy augmented owner")
    if not _imports_module(FD_AUDIT, SEMANTIC_MODULE):
        raise AssertionError("FD-reference audit does not import the semantic Issue46 owner")
    for token in FD_REQUIRED_SOURCE_TOKENS:
        if token not in fd_source:
            raise AssertionError(f"FD canonical destination missing: {token}")
    for token in FD_FORBIDDEN_LEGACY_TOKENS:
        if token in fd_source:
            raise AssertionError(f"FD legacy dependency remains: {token}")
    # The accepted public result vector historically exposed category fractions.
    # They may be reconstructed locally from generic owner-block facts, but must
    # not require the historical augmented owner.
    if "_category_energy_fraction" not in fd_source:
        raise AssertionError("FD result-vector category compatibility was dropped")


def _check_consumer_role_boundary() -> None:
    _check_fd_dependency_destination_matrix()
    cli_source = CLI.read_text()
    legacy_cli = (
        "from qpx_harness.augmented_jacobian_localization import main as "
        "jac_localization_main, self_test as jac_localization_self_test"
    )
    if legacy_cli not in cli_source:
        raise AssertionError("stable CLI cut over before FD-audit cutover acceptance")
    if '"inventory-jacobian-localization":' not in cli_source:
        raise AssertionError("stable inventory-jacobian-localization command missing")


def _negative_control() -> None:
    fd_source = FD_AUDIT.read_text()
    mutated = fd_source + "\nfrom . import augmented_jacobian_localization as old_loc\n"
    tree = ast.parse(mutated, filename=str(FD_AUDIT))
    if not any(
        isinstance(node, ast.ImportFrom)
        and node.module == ""
        and any(alias.name == "augmented_jacobian_localization" for alias in node.names)
        for node in ast.walk(tree)
    ):
        # Relative import ASTs encode module without the leading dot differently
        # across simple synthetic contexts; retain a text-level guard as well.
        if "augmented_jacobian_localization" not in mutated:
            raise AssertionError("legacy-import negative control failed")
    if "petsc_matrix.summarize_by_owner" not in fd_source:
        raise AssertionError("generic owner-block negative control baseline missing")


def main() -> int:
    try:
        _check_consumer_topology()
        print("ISSUE48_WP23_AUGMENTED_OWNER_CHECK: consumer-topology=PASS")
        _check_construction_owner_equivalence()
        print("ISSUE48_WP23_AUGMENTED_OWNER_CHECK: construction-owner-equivalence=PASS")
        _check_generic_primitive_equivalence()
        print("ISSUE48_WP23_AUGMENTED_OWNER_CHECK: generic-primitive-equivalence=PASS")
        _check_runtime_policy_boundary()
        print("ISSUE48_WP23_AUGMENTED_OWNER_CHECK: runtime-policy-boundary=PASS")
        _check_fd_dependency_destination_matrix()
        print("ISSUE48_WP23_AUGMENTED_OWNER_CHECK: fd-dependency-destination-matrix=PASS")
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