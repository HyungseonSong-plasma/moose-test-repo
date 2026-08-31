#!/usr/bin/env python3
"""P0 convergence characterization for the retired-boundary Issue46 augmented owner."""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import electron_inventory_nullspace as inv
from qpx_harness import issue46_jacobian_localization as semantic
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

EXPECTED_SEMANTIC_PRODUCTION_CONSUMERS = {
    "qpx_harness/jacobian_fd_reference_audit.py",
    "scripts/qpx.py",
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

FD_REQUIRED_SOURCE_TOKENS = (
    "from recipes import issue46_jacobian_localization as localization_recipe",
    "from . import issue46_jacobian_localization as localization_runtime",
    "from .moose import dofmap as dm",
    "from .petsc import matrix as petsc_matrix",
    "from .petsc import options as petsc_options",
    "localization_recipe.instrument_localization",
    "localization_runtime.audit_localization_structure",
    "dm.parse_dof_map_text",
    "petsc_matrix.parse_threshold_difference_matrix",
    "petsc_matrix.summarize_by_owner",
    "petsc_options.get_name_value_pairs",
    "petsc_options.set_name_value_pairs",
    "petsc_options.upsert_name_value",
)


def _resolved_imports(path: Path) -> set[str]:
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
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
            if base:
                result.add(base)
            for alias in node.names:
                if alias.name != "*":
                    result.add(f"{base}.{alias.name}" if base else alias.name)
    return result


def _dynamic_imports(path: Path) -> set[str]:
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    constants: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, (ast.Assign, ast.AnnAssign))
            and isinstance(getattr(node, "value", None), ast.Constant)
            and isinstance(node.value.value, str)
        ):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = node.value.value

    result: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        is_import_module = (
            isinstance(func, ast.Name) and func.id in {"import_module", "__import__"}
        ) or (
            isinstance(func, ast.Attribute)
            and func.attr == "import_module"
            and isinstance(func.value, ast.Name)
            and func.value.id == "importlib"
        )
        if not is_import_module:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            result.add(arg.value)
        elif isinstance(arg, ast.Name) and arg.id in constants:
            result.add(constants[arg.id])
    return result


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
                consumes = (
                    module_name in _resolved_imports(path)
                    or module_name in _dynamic_imports(path)
                )
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
    _assert_equal("legacy production consumers", legacy_prod, set())
    _assert_equal("legacy test consumers", legacy_tests, set())

    semantic_prod, _ = _consumer_sets(SEMANTIC_MODULE, SEMANTIC)
    _assert_equal(
        "semantic production consumers",
        semantic_prod,
        EXPECTED_SEMANTIC_PRODUCTION_CONSUMERS,
    )


def _check_construction_owner_equivalence() -> None:
    for name in ("TARGET", "LOCALIZATION_THRESHOLD", "DOFMAP_OUTPUT", "DOFMAP_FILE_BASE"):
        _assert_equal(f"recipe/semantic {name}", getattr(recipe, name), getattr(semantic, name))
    base = inv._synthetic_constrained_input(recipe.TARGET)
    first_text, _ = first_linear.instrument_first_linear(base)
    recipe_text, recipe_meta = recipe.instrument_localization(first_text)
    semantic_text, semantic_meta = semantic.instrument_localization(first_text)
    _assert_equal("recipe/semantic construction text", recipe_text, semantic_text)
    _assert_equal("recipe/semantic metadata", recipe_meta, semantic_meta)


def _check_generic_primitive_equivalence() -> None:
    dofmap_text = semantic._synthetic_dof_map()
    semantic_dofmap = semantic.parse_dof_map_text(dofmap_text)
    generic_dofmap = dm.parse_dof_map_text(
        dofmap_text,
        expected_variables=semantic.MAIN_VARIABLES,
        scalar_variables=semantic.SCALAR_VARIABLES,
    )
    _assert_equal("DOF ownership generic/semantic", generic_dofmap, semantic_dofmap)

    log = semantic._synthetic_localization_log([(0, 4, 2.0e-4), (4, 1, -3.0e-4)])
    semantic_difference = semantic.parse_threshold_difference_matrix(log)
    generic_difference = pm.parse_threshold_difference_matrix(log)
    _assert_equal("matrix generic/semantic", generic_difference, semantic_difference)

    semantic_localized = semantic.localize_difference_entries(
        semantic_difference, semantic_dofmap
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
        _assert_equal(f"generic fact {key}", generic_localized[key], semantic_localized[key])

    base = inv._synthetic_constrained_input(recipe.TARGET)
    first_text, _ = first_linear.instrument_first_linear(base)
    localized_text, _ = recipe.instrument_localization(first_text)
    pairs = po.get_name_value_pairs(localized_text)
    _assert_equal(
        "PETSc write/read round trip",
        po.get_name_value_pairs(po.set_name_value_pairs(localized_text, pairs)),
        pairs,
    )
    if ("-mat_fd_type", "ds") not in po.get_name_value_pairs(
        po.upsert_name_value(localized_text, "-mat_fd_type", "ds")
    ):
        raise AssertionError("generic PETSc upsert lost -mat_fd_type ds")


def _check_runtime_policy_boundary() -> None:
    if not SEMANTIC.is_file():
        raise AssertionError("semantic Issue46 localization owner is missing")
    if LEGACY_MODULE in _resolved_imports(SEMANTIC) or LEGACY_MODULE in _dynamic_imports(SEMANTIC):
        raise AssertionError("semantic Issue46 owner reverse-depends on legacy owner")
    for name in RUNTIME_POLICY_SURFACE:
        if not callable(getattr(semantic, name, None)):
            raise AssertionError(f"semantic runtime surface missing: {name}")


def _check_fd_dependency_destination_matrix() -> None:
    fd_source = FD_AUDIT.read_text()
    if LEGACY_MODULE in _resolved_imports(FD_AUDIT) or LEGACY_MODULE in _dynamic_imports(FD_AUDIT):
        raise AssertionError("FD-reference audit still imports the legacy augmented owner")
    if SEMANTIC_MODULE not in _resolved_imports(FD_AUDIT):
        raise AssertionError("FD-reference audit does not import the semantic Issue46 owner")
    for token in FD_REQUIRED_SOURCE_TOKENS:
        if token not in fd_source:
            raise AssertionError(f"FD canonical destination missing: {token}")
    if "_category_energy_fraction" not in fd_source:
        raise AssertionError("FD result-vector category compatibility was dropped")


def _check_consumer_role_boundary() -> None:
    _check_fd_dependency_destination_matrix()
    cli_source = CLI.read_text()
    semantic_cli = (
        "from qpx_harness.issue46_jacobian_localization import main as "
        "jac_localization_main, self_test as jac_localization_self_test"
    )
    if semantic_cli not in cli_source:
        raise AssertionError("stable CLI does not route localization to semantic owner")
    if "from qpx_harness.augmented_jacobian_localization import" in cli_source:
        raise AssertionError("stable CLI still imports legacy augmented owner")
    if '"inventory-jacobian-localization":' not in cli_source:
        raise AssertionError("stable inventory-jacobian-localization command missing")


def _negative_control() -> None:
    probe = ROOT / "tests" / "Issue48_qpx_harness_generality" / "_dynamic_probe.py"
    source = (
        "import importlib\n"
        f"LEGACY = {LEGACY_MODULE!r}\n"
        "legacy = importlib.import_module(LEGACY)\n"
    )
    tree = ast.parse(source, filename=str(probe))
    constants = {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    detected = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and constants.get(node.args[0].id) == LEGACY_MODULE
        ):
            detected = True
    if not detected:
        raise AssertionError("dynamic legacy-import negative control failed")


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
