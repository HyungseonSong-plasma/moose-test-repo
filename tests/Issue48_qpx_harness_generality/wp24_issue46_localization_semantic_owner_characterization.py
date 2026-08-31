#!/usr/bin/env python3
"""P0 characterization for the canonical Issue46 localization semantic runtime owner."""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import electron_inventory_nullspace as inv
from qpx_harness import issue46_jacobian_localization as semantic
from recipes import issue45_first_linear as first_linear
from recipes import issue46_jacobian_localization as recipe

LEGACY_MODULE = "qpx_harness.augmented_jacobian_localization"
SEMANTIC_PATH = ROOT / "qpx_harness" / "issue46_jacobian_localization.py"
CLI_PATH = ROOT / "scripts" / "qpx.py"
FD_AUDIT_PATH = ROOT / "qpx_harness" / "jacobian_fd_reference_audit.py"

RUNTIME_SURFACE = (
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


def _check_owner_topology() -> None:
    if not SEMANTIC_PATH.is_file():
        raise AssertionError("semantic Issue46 localization owner is missing")
    source = SEMANTIC_PATH.read_text()
    tree = ast.parse(source, filename=str(SEMANTIC_PATH))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == LEGACY_MODULE for alias in node.names):
                raise AssertionError("semantic owner imports legacy owner")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.endswith("augmented_jacobian_localization"):
                raise AssertionError("semantic owner reverse-depends on legacy owner")
            if module == "qpx_harness" and any(
                alias.name == "augmented_jacobian_localization" for alias in node.names
            ):
                raise AssertionError("semantic owner reverse-depends on legacy owner")

    cli = CLI_PATH.read_text()
    if "from qpx_harness.issue46_jacobian_localization import" not in cli:
        raise AssertionError("CLI does not route to semantic Issue46 localization owner")
    if "from qpx_harness.augmented_jacobian_localization import" in cli:
        raise AssertionError("CLI still imports legacy augmented owner")

    fd = FD_AUDIT_PATH.read_text()
    if "from . import augmented_jacobian_localization" in fd:
        raise AssertionError("FD audit still reverse-depends on legacy augmented owner")
    required_fd = (
        "from recipes import issue46_jacobian_localization as localization_recipe",
        "from . import issue46_jacobian_localization as localization_runtime",
        "from .moose import dofmap as dm",
        "from .petsc import matrix as petsc_matrix",
        "from .petsc import options as petsc_options",
    )
    for token in required_fd:
        if token not in fd:
            raise AssertionError(f"FD audit missing canonical cutover dependency: {token}")


def _check_recipe_identity_and_construction() -> None:
    for name in ("TARGET", "LOCALIZATION_THRESHOLD", "DOFMAP_OUTPUT", "DOFMAP_FILE_BASE"):
        if getattr(recipe, name) != getattr(semantic, name):
            raise AssertionError(f"recipe/semantic {name} drift")
    if semantic.instrument_localization is not recipe.instrument_localization:
        raise AssertionError("semantic owner does not delegate construction to recipe")

    base = inv._synthetic_constrained_input(recipe.TARGET)
    first_text, _ = first_linear.instrument_first_linear(base)
    recipe_text, recipe_meta = recipe.instrument_localization(first_text)
    semantic_text, semantic_meta = semantic.instrument_localization(first_text)
    if semantic_text != recipe_text or semantic_meta != recipe_meta:
        raise AssertionError("semantic construction drifted from recipe")


def _check_structure_equivalence() -> None:
    base = inv._synthetic_constrained_input(recipe.TARGET)
    first_text, _ = first_linear.instrument_first_linear(base)
    localized, _ = recipe.instrument_localization(first_text)
    if semantic.audit_localization_structure(first_text, localized)["status"] != "PASS":
        raise AssertionError("canonical localization structure did not pass")

    for label, candidate in (
        (
            "wrong-dofmap",
            localized.replace("file_base = r46_dofmap", "file_base = wrong_dofmap", 1),
        ),
        ("wrong-nl-horizon", localized.replace("nl_max_its = 1", "nl_max_its = 2", 1)),
    ):
        if semantic.audit_localization_structure(first_text, candidate)["status"] == "PASS":
            raise AssertionError(f"localization structure mutation passed: {label}")

    control = semantic.build_framework_control_input()
    if semantic.audit_framework_control_structure(control)["status"] != "PASS":
        raise AssertionError("canonical framework control did not pass")
    for label, candidate in (
        (
            "off-diagonal-scaling",
            control.replace(
                "off_diagonals_in_auto_scaling = true",
                "off_diagonals_in_auto_scaling = false",
                1,
            ),
        ),
        ("operator", control.replace("type = FVDiffusion", "type = FVElementalAdvection", 1)),
        ("coefficient", control.replace("coeff = 1", "coeff = 2", 1)),
    ):
        if semantic.audit_framework_control_structure(candidate)["status"] == "PASS":
            raise AssertionError(f"framework-control mutation passed: {label}")


def _check_fact_and_analysis_equivalence() -> None:
    dofmap = semantic._synthetic_dof_map()
    parsed_dofmap = semantic.parse_dof_map_text(dofmap)
    if parsed_dofmap.get("ndof") is None or not parsed_dofmap.get("owner_by_dof"):
        raise AssertionError("semantic DOFMap parser lost ownership facts")

    logs = (
        semantic._synthetic_localization_log([(0, 4, 2.0e-4), (4, 1, -3.0e-4)]),
        semantic._synthetic_localization_log([(0, 2, 2.0e-4), (3, 1, -3.0e-4)]),
        semantic._synthetic_localization_log([(0, 1, 2.0e-4), (2, 3, -3.0e-4)]),
        semantic._synthetic_localization_log([]),
    )
    for log in logs:
        difference = semantic.parse_threshold_difference_matrix(log)
        localized = semantic.localize_difference_entries(difference, parsed_dofmap)
        for key in (
            "blocks",
            "entry_count",
            "mapped_entry_count",
            "thresholded_l2_difference",
            "category_energy_fraction",
        ):
            if key not in localized:
                raise AssertionError(f"semantic localization result missing {key}")
        analysis = semantic.analyze_localization_text(log, dofmap)
        if analysis.get("status") not in {"PASS", "HOLD"}:
            raise AssertionError("semantic localization analysis returned invalid status")

    missing_view = logs[0].split("Hand-coded minus finite-difference", 1)[0]
    missing = semantic.analyze_localization_text(missing_view, dofmap)
    if missing.get("status") != "HOLD":
        raise AssertionError("missing matrix view was not held")


def _check_runtime_policy_equivalence() -> None:
    good = semantic.analyze_framework_control_runtime(
        semantic._synthetic_jacobian_log(1.0e-9), returncode=0
    )
    bad = semantic.analyze_framework_control_runtime(
        semantic._synthetic_jacobian_log(1.0e-6), returncode=0
    )
    if good.get("status") != "PASS":
        raise AssertionError("framework-control positive runtime fixture did not pass")
    if bad.get("status") == "PASS":
        raise AssertionError("framework-control negative runtime fixture passed")

    dofmap = semantic._synthetic_dof_map()
    localization = semantic.analyze_localization_text(
        semantic._synthetic_localization_log([(0, 4, 2.0e-4), (4, 1, -3.0e-4)]),
        dofmap,
    )
    for control, local in ((good, localization), (bad, localization), (good, None)):
        decision = semantic.evaluate_runtime_batch(control, local)
        if decision.get("status") not in {"PASS", "HOLD"}:
            raise AssertionError("runtime batch decision returned invalid status")


def _check_runtime_surface() -> None:
    for name in RUNTIME_SURFACE:
        obj = getattr(semantic, name, None)
        if not callable(obj):
            raise AssertionError(f"semantic runtime surface missing: {name}")
        if name in {"_prepare_cases", "run_preflight", "run_runtime", "main"}:
            inspect.signature(obj)

    source = SEMANTIC_PATH.read_text()
    required = (
        "from recipes import issue46_jacobian_localization as localization_recipe",
        "from .moose import dofmap as dm",
        "from .petsc import matrix as pm",
        "from .petsc import options as po",
    )
    for token in required:
        if token not in source:
            raise AssertionError(f"semantic owner missing canonical composition: {token}")


def _check_self_test_equivalence() -> None:
    if semantic.self_test() != 0:
        raise AssertionError("semantic Issue46 localization self-test failed")


def _negative_control() -> None:
    base = inv._synthetic_constrained_input(recipe.TARGET)
    first_text, _ = first_linear.instrument_first_linear(base)
    localized, _ = recipe.instrument_localization(first_text)
    mutated = localized.replace("file_base = r46_dofmap", "file_base = wrong_dofmap", 1)
    if semantic.audit_localization_structure(first_text, mutated)["status"] == "PASS":
        raise AssertionError("semantic owner accepted DOFMap mutation")
    bad_dofmap = semantic._synthetic_dof_map().replace('"ndof": 5', '"ndof": 4', 1)
    try:
        semantic.parse_dof_map_text(bad_dofmap)
    except semantic.Issue46JacobianLocalizationError:
        pass
    else:
        raise AssertionError("semantic owner accepted invalid DOF ownership mutation")


def main() -> int:
    try:
        _check_owner_topology()
        print("ISSUE48_WP24_ISSUE46_SEMANTIC_CHECK: dual-owner-topology=PASS")
        _check_recipe_identity_and_construction()
        print("ISSUE48_WP24_ISSUE46_SEMANTIC_CHECK: recipe-construction-identity=PASS")
        _check_structure_equivalence()
        print("ISSUE48_WP24_ISSUE46_SEMANTIC_CHECK: structure-equivalence=PASS")
        _check_fact_and_analysis_equivalence()
        print("ISSUE48_WP24_ISSUE46_SEMANTIC_CHECK: analysis-equivalence=PASS")
        _check_runtime_policy_equivalence()
        print("ISSUE48_WP24_ISSUE46_SEMANTIC_CHECK: runtime-policy-equivalence=PASS")
        _check_runtime_surface()
        print("ISSUE48_WP24_ISSUE46_SEMANTIC_CHECK: runtime-surface=PASS")
        _check_self_test_equivalence()
        print("ISSUE48_WP24_ISSUE46_SEMANTIC_CHECK: self-test-equivalence=PASS")
        _negative_control()
        print("ISSUE48_WP24_ISSUE46_SEMANTIC_CHECK: negative-control=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP24_ISSUE46_SEMANTIC_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP24_ISSUE46_SEMANTIC_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
