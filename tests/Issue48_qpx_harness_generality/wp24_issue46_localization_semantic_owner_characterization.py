#!/usr/bin/env python3
"""P0 dual-owner equivalence for the Issue46 localization semantic runtime owner."""
from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import electron_inventory_nullspace as inv
from recipes import issue45_first_linear as first_linear
from recipes import issue46_jacobian_localization as recipe

LEGACY_MODULE = "qpx_harness.augmented_jacobian_localization"
SEMANTIC_MODULE = "qpx_harness.issue46_jacobian_localization"
LEGACY_PATH = ROOT / "qpx_harness" / "augmented_jacobian_localization.py"
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


def _legacy() -> Any:
    return importlib.import_module(LEGACY_MODULE)


def _semantic() -> Any:
    return importlib.import_module(SEMANTIC_MODULE)


def _assert_equal(label: str, left: object, right: object) -> None:
    if left != right:
        raise AssertionError(f"{label} drift:\nlegacy={left!r}\nsemantic={right!r}")


def _check_owner_topology() -> None:
    if not LEGACY_PATH.is_file():
        raise AssertionError("legacy augmented owner unexpectedly absent before cutover")
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
    if "from qpx_harness.augmented_jacobian_localization import" not in cli:
        raise AssertionError("CLI cut over before semantic-owner equivalence acceptance")
    fd = FD_AUDIT_PATH.read_text()
    if "from . import augmented_jacobian_localization as loc" not in fd:
        raise AssertionError("FD audit cut over before semantic-owner equivalence acceptance")


def _check_recipe_identity_and_construction() -> None:
    legacy = _legacy()
    semantic = _semantic()
    for name in ("TARGET", "LOCALIZATION_THRESHOLD", "DOFMAP_OUTPUT", "DOFMAP_FILE_BASE"):
        _assert_equal(f"legacy/semantic {name}", getattr(legacy, name), getattr(semantic, name))
        _assert_equal(f"recipe/semantic {name}", getattr(recipe, name), getattr(semantic, name))
    if semantic.instrument_localization is not recipe.instrument_localization:
        raise AssertionError("semantic owner does not delegate construction to recipe")

    base = inv._synthetic_constrained_input(recipe.TARGET)
    first_text, _ = first_linear.instrument_first_linear(base)
    legacy_text, legacy_meta = legacy.instrument_localization(first_text)
    semantic_text, semantic_meta = semantic.instrument_localization(first_text)
    _assert_equal("construction text", legacy_text, semantic_text)
    _assert_equal("construction metadata", legacy_meta, semantic_meta)


def _check_structure_equivalence() -> None:
    legacy = _legacy()
    semantic = _semantic()
    base = inv._synthetic_constrained_input(recipe.TARGET)
    first_text, _ = first_linear.instrument_first_linear(base)
    localized, _ = recipe.instrument_localization(first_text)
    for candidate in (
        localized,
        localized.replace("file_base = r46_dofmap", "file_base = wrong_dofmap", 1),
        localized.replace("nl_max_its = 1", "nl_max_its = 2", 1),
    ):
        _assert_equal(
            "localization structure audit",
            legacy.audit_localization_structure(first_text, candidate),
            semantic.audit_localization_structure(first_text, candidate),
        )

    legacy_control = legacy.build_framework_control_input()
    semantic_control = semantic.build_framework_control_input()
    _assert_equal("framework control input", legacy_control, semantic_control)
    for candidate in (
        legacy_control,
        legacy_control.replace(
            "off_diagonals_in_auto_scaling = true",
            "off_diagonals_in_auto_scaling = false",
            1,
        ),
        legacy_control.replace("type = FVDiffusion", "type = FVElementalAdvection", 1),
        legacy_control.replace("coeff = 1", "coeff = 2", 1),
    ):
        _assert_equal(
            "framework control audit",
            legacy.audit_framework_control_structure(candidate),
            semantic.audit_framework_control_structure(candidate),
        )


def _check_fact_and_analysis_equivalence() -> None:
    legacy = _legacy()
    semantic = _semantic()
    dofmap = legacy._synthetic_dof_map()
    _assert_equal("DOFMap parse", legacy.parse_dof_map_text(dofmap), semantic.parse_dof_map_text(dofmap))

    logs = (
        legacy._synthetic_localization_log([(0, 4, 2.0e-4), (4, 1, -3.0e-4)]),
        legacy._synthetic_localization_log([(0, 2, 2.0e-4), (3, 1, -3.0e-4)]),
        legacy._synthetic_localization_log([(0, 1, 2.0e-4), (2, 3, -3.0e-4)]),
        legacy._synthetic_localization_log([]),
    )
    for log in logs:
        legacy_diff = legacy.parse_threshold_difference_matrix(log)
        semantic_diff = semantic.parse_threshold_difference_matrix(log)
        _assert_equal("threshold matrix parse", legacy_diff, semantic_diff)
        legacy_loc = legacy.localize_difference_entries(
            legacy_diff, legacy.parse_dof_map_text(dofmap)
        )
        semantic_loc = semantic.localize_difference_entries(
            semantic_diff, semantic.parse_dof_map_text(dofmap)
        )
        _assert_equal("localized owner facts/policy", legacy_loc, semantic_loc)
        _assert_equal(
            "localization analysis",
            legacy.analyze_localization_text(log, dofmap),
            semantic.analyze_localization_text(log, dofmap),
        )

    missing_view = logs[0].split("Hand-coded minus finite-difference", 1)[0]
    _assert_equal(
        "missing-view classification",
        legacy.analyze_localization_text(missing_view, dofmap),
        semantic.analyze_localization_text(missing_view, dofmap),
    )
    _assert_equal(
        "framework-control-fail precedence",
        legacy.analyze_localization_text(logs[0], dofmap, framework_control_pass=False),
        semantic.analyze_localization_text(logs[0], dofmap, framework_control_pass=False),
    )


def _check_runtime_policy_equivalence() -> None:
    legacy = _legacy()
    semantic = _semantic()
    for rel in (1.0e-9, 1.0e-6):
        log = legacy._synthetic_jacobian_log(rel)
        _assert_equal(
            f"framework runtime rel={rel}",
            legacy.analyze_framework_control_runtime(log, returncode=0),
            semantic.analyze_framework_control_runtime(log, returncode=0),
        )

    control_pass = legacy.analyze_framework_control_runtime(
        legacy._synthetic_jacobian_log(1.0e-9), returncode=0
    )
    control_fail = legacy.analyze_framework_control_runtime(
        legacy._synthetic_jacobian_log(1.0e-6), returncode=0
    )
    dofmap = legacy._synthetic_dof_map()
    localization = legacy.analyze_localization_text(
        legacy._synthetic_localization_log([(0, 4, 2.0e-4), (4, 1, -3.0e-4)]),
        dofmap,
    )
    for control, local in (
        (control_pass, localization),
        (control_fail, localization),
        (control_pass, None),
    ):
        _assert_equal(
            "runtime batch decision",
            legacy.evaluate_runtime_batch(control, local),
            semantic.evaluate_runtime_batch(control, local),
        )


def _check_runtime_surface() -> None:
    legacy = _legacy()
    semantic = _semantic()
    for name in RUNTIME_SURFACE:
        legacy_obj = getattr(legacy, name, None)
        semantic_obj = getattr(semantic, name, None)
        if not callable(legacy_obj) or not callable(semantic_obj):
            raise AssertionError(f"runtime surface missing: {name}")
        if name in {"_prepare_cases", "run_preflight", "run_runtime", "main"}:
            _assert_equal(
                f"runtime signature {name}",
                inspect.signature(legacy_obj),
                inspect.signature(semantic_obj),
            )

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
    legacy = _legacy()
    semantic = _semantic()
    legacy_rc = legacy.self_test()
    semantic_rc = semantic.self_test()
    if legacy_rc != 0 or semantic_rc != 0 or legacy_rc != semantic_rc:
        raise AssertionError(
            f"self-test equivalence failed: legacy={legacy_rc}, semantic={semantic_rc}"
        )


def _negative_control() -> None:
    semantic = _semantic()
    base = inv._synthetic_constrained_input(recipe.TARGET)
    first_text, _ = first_linear.instrument_first_linear(base)
    localized, _ = recipe.instrument_localization(first_text)
    mutated = localized.replace("file_base = r46_dofmap", "file_base = wrong_dofmap", 1)
    if semantic.audit_localization_structure(first_text, mutated)["status"] == "PASS":
        raise AssertionError("semantic owner accepted DOFMap mutation")
    control = semantic.build_framework_control_input().replace("coeff = 1", "coeff = 2", 1)
    if semantic.audit_framework_control_structure(control)["status"] == "PASS":
        raise AssertionError("semantic owner accepted framework-control coefficient mutation")
    bad_dofmap = dofmap = semantic._synthetic_dof_map().replace('"ndof": 5', '"ndof": 4', 1)
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
