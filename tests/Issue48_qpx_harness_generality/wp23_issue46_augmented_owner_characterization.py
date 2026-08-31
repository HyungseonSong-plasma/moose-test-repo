#!/usr/bin/env python3
"""P0 boundary characterization for Issue46 augmented-localization convergence."""
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
from qpx_harness.petsc import options as po
from recipes import issue45_first_linear as first_linear
from recipes import issue46_jacobian_localization as recipe

LEGACY_MODULE = "qpx_harness.augmented_jacobian_localization"
SEMANTIC_MODULE = "qpx_harness.issue46_jacobian_localization"
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
FD_EXPECTED_LOC_SYMBOLS = {
    "AugmentedJacobianLocalizationError",
    "DOFMAP_FILE_BASE",
    "LOCALIZATION_THRESHOLD",
    "_petsc_name_value_pairs",
    "_set_petsc_name_value_pairs",
    "_upsert_petsc_value",
    "audit_localization_structure",
    "instrument_localization",
    "localize_difference_entries",
    "parse_dof_map_text",
    "parse_threshold_difference_matrix",
}
FD_RECIPE_SYMBOLS = {
    "DOFMAP_FILE_BASE",
    "LOCALIZATION_THRESHOLD",
    "instrument_localization",
}
FD_GENERIC_PETSC_SYMBOLS = {
    "_petsc_name_value_pairs": "get_name_value_pairs",
    "_set_petsc_name_value_pairs": "set_name_value_pairs",
    "_upsert_petsc_value": "upsert_name_value",
}
FD_GENERIC_FACT_SYMBOLS = {
    "parse_dof_map_text": "parse_dof_map_text",
    "parse_threshold_difference_matrix": "parse_threshold_difference_matrix",
    "localize_difference_entries": "summarize_by_owner",
}
FD_SEMANTIC_RUNTIME_SYMBOLS = {"audit_localization_structure"}
FD_ERROR_ADAPTER_SYMBOLS = {"AugmentedJacobianLocalizationError"}


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
    production, tests = _consumer_sets(LEGACY_MODULE, LEGACY)
    _assert_equal("legacy production consumers", production, EXPECTED_PRODUCTION_CONSUMERS)
    _assert_equal("legacy test consumers", tests, EXPECTED_TEST_CONSUMERS)
    semantic_prod, semantic_tests = _consumer_sets(SEMANTIC_MODULE, SEMANTIC)
    _assert_equal("semantic production consumers", semantic_prod, set())
    _assert_equal("semantic test consumers", semantic_tests, set())


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
    recipe_source = Path(recipe.__file__).read_text()
    if "augmented_jacobian_localization" in recipe_source or "issue46_jacobian_localization" in recipe_source:
        raise AssertionError("Issue46 construction recipe reverse-depends on runtime owner")


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
    _assert_equal("DOF ownership semantic/legacy", semantic.parse_dof_map_text(dofmap_text), legacy_dofmap)

    log = legacy._synthetic_localization_log([(0, 4, 2.0e-4), (4, 1, -3.0e-4)])
    legacy_difference = legacy.parse_threshold_difference_matrix(log)
    generic_difference = pm.parse_threshold_difference_matrix(log)
    _assert_equal("matrix generic/legacy", generic_difference, legacy_difference)
    _assert_equal("matrix semantic/legacy", semantic.parse_threshold_difference_matrix(log), legacy_difference)

    legacy_localized = legacy.localize_difference_entries(legacy_difference, legacy_dofmap)
    semantic_localized = semantic.localize_difference_entries(generic_difference, generic_dofmap)
    _assert_equal("semantic localization facts", semantic_localized, legacy_localized)
    generic_localized = pm.summarize_by_owner(generic_difference, generic_dofmap["owner_by_dof"])
    for key in ("blocks", "unmapped_entries", "entry_count", "mapped_entry_count", "thresholded_l2_difference"):
        _assert_equal(f"generic fact {key}", generic_localized[key], legacy_localized[key])

    base = inv._synthetic_constrained_input(recipe.TARGET)
    first_text, _ = first_linear.instrument_first_linear(base)
    localized_text, _ = recipe.instrument_localization(first_text)
    legacy_pairs = legacy._petsc_name_value_pairs(localized_text)
    generic_pairs = po.get_name_value_pairs(localized_text)
    _assert_equal("PETSc read", generic_pairs, legacy_pairs)
    _assert_equal("PETSc write", po.set_name_value_pairs(localized_text, generic_pairs), legacy._set_petsc_name_value_pairs(localized_text, legacy_pairs))
    _assert_equal("PETSc upsert", po.upsert_name_value(localized_text, "-mat_fd_type", "ds"), legacy._upsert_petsc_value(localized_text, "-mat_fd_type", "ds"))


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
    semantic_source = SEMANTIC.read_text()
    for token in (
        "from recipes import issue46_jacobian_localization",
        "from .moose import dofmap",
        "from .petsc import matrix",
        "from .petsc import options",
    ):
        if token not in semantic_source:
            raise AssertionError(f"semantic owner does not compose canonical layer: {token}")


def _loc_symbols(source: str) -> set[str]:
    return set(re.findall(r"\bloc\.([A-Za-z_][A-Za-z0-9_]*)", source))


def _check_fd_dependency_destination_matrix() -> None:
    legacy = _module(LEGACY_MODULE)
    semantic = _module(SEMANTIC_MODULE)
    fd_source = FD_AUDIT.read_text()
    if "from . import augmented_jacobian_localization as loc" not in fd_source:
        raise AssertionError("FD-reference consumer import shape drifted before cutover")
    observed = _loc_symbols(fd_source)
    _assert_equal("FD legacy symbol surface", observed, FD_EXPECTED_LOC_SYMBOLS)
    classified = (
        FD_RECIPE_SYMBOLS
        | set(FD_GENERIC_PETSC_SYMBOLS)
        | set(FD_GENERIC_FACT_SYMBOLS)
        | FD_SEMANTIC_RUNTIME_SYMBOLS
        | FD_ERROR_ADAPTER_SYMBOLS
    )
    _assert_equal("FD destination matrix coverage", classified, FD_EXPECTED_LOC_SYMBOLS)
    for name in FD_RECIPE_SYMBOLS:
        if not hasattr(recipe, name):
            raise AssertionError(f"recipe destination missing: {name}")
    for old_name, new_name in FD_GENERIC_PETSC_SYMBOLS.items():
        if not hasattr(legacy, old_name) or not callable(getattr(po, new_name, None)):
            raise AssertionError(f"PETSc destination unavailable: {old_name}->{new_name}")
    for new_name in FD_GENERIC_FACT_SYMBOLS.values():
        if not callable(getattr(dm if new_name == "parse_dof_map_text" else pm, new_name, None)):
            raise AssertionError(f"generic fact destination unavailable: {new_name}")
    for name in FD_SEMANTIC_RUNTIME_SYMBOLS:
        if not callable(getattr(semantic, name, None)):
            raise AssertionError(f"semantic destination unavailable: {name}")
    if "category_energy_fraction" in fd_source:
        raise AssertionError("FD consumer now depends on Issue46 category-energy policy")


def _check_consumer_role_boundary() -> None:
    _check_fd_dependency_destination_matrix()
    cli_source = CLI.read_text()
    legacy_cli = (
        "from qpx_harness.augmented_jacobian_localization import main as "
        "jac_localization_main, self_test as jac_localization_self_test"
    )
    if legacy_cli not in cli_source:
        raise AssertionError("stable CLI cut over before dual-owner validation")
    if '"inventory-jacobian-localization":' not in cli_source:
        raise AssertionError("stable inventory-jacobian-localization command missing")


def _negative_control() -> None:
    fd_source = FD_AUDIT.read_text()
    if _loc_symbols(fd_source + "\nloc.run_runtime\n") == FD_EXPECTED_LOC_SYMBOLS:
        raise AssertionError("FD dependency-surface mutation was not detected")
    semantic_source = SEMANTIC.read_text()
    tree = ast.parse(semantic_source, filename=str(SEMANTIC))
    if not any(isinstance(node, ast.ImportFrom) for node in ast.walk(tree)):
        raise AssertionError("semantic-owner AST control did not observe imports")


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
