#!/usr/bin/env python3
"""P0 characterization for completed fast_plasma_relaxation_v2 retirement."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import issue43_relaxation_runtime as runtime43

V2 = ROOT / "qpx_harness" / "fast_plasma_relaxation_v2.py"
EXPECTED_RUNTIME_CONSUMERS: set[str] = set()


def _source(name: str) -> str:
    return (ROOT / "qpx_harness" / name).read_text()


def _observed_consumers() -> dict[str, str]:
    result: dict[str, str] = {}
    tokens = (
        "from . import fast_plasma_relaxation_v2 as v2",
        "import qpx_harness.fast_plasma_relaxation_v2 as v2",
    )
    for path in (ROOT / "qpx_harness").glob("*.py"):
        text = path.read_text()
        if any(token in text for token in tokens):
            result[path.name] = text
    return result


def _check_consumer_topology() -> None:
    observed = _observed_consumers()
    if set(observed) != EXPECTED_RUNTIME_CONSUMERS:
        raise AssertionError(
            f"v2 consumer drift: observed={sorted(observed)} expected={sorted(EXPECTED_RUNTIME_CONSUMERS)}"
        )

    v5 = _source("fast_plasma_relaxation_v5.py")
    for forbidden in (
        "fast_plasma_relaxation_v2",
        "v2.",
        "_install_v2_repairs(",
        "_install_v5_repairs(",
    ):
        if forbidden in v5:
            raise AssertionError(f"v5 retained retired v2 runtime dependency: {forbidden}")
    for token in (
        "from . import issue43_relaxation_runtime as issue43_runtime",
        "_RAW_BUILD_ELECTRON_300K = issue43_runtime.build_electron_300k",
        "_RAW_BUILD_ONEWAY = issue43_runtime.build_oneway",
        "_RAW_BUILD_FEEDBACK = issue43_runtime.build_feedback",
        "_RAW_RUN_CASE = issue43_runtime.run_case",
        "_RAW_CLASSIFY = relaxation_recipe.classify",
        "issue43_runtime.run_known_good(",
        "issue43_runtime.physics_pass(",
        "issue43_runtime.attach_nonlinear_residual(",
    ):
        if token not in v5:
            raise AssertionError(f"v5 canonical Issue43 runtime cutover drift: {token}")


def _check_v2_retired() -> None:
    if V2.exists():
        raise AssertionError("retired fast_plasma_relaxation_v2.py still exists")


def _check_remaining_stale_refs() -> None:
    for name in (
        "augmented_jacobian_localization.py",
        "electron_inventory_nullspace.py",
        "fast_plasma_coupling_diagnostic.py",
        "jacobian_fd_reference_audit.py",
        "petsc_first_linear_diagnostic.py",
    ):
        source = _source(name)
        for token in ("fast_plasma_relaxation_v2", "v2.v1."):
            if token in source:
                raise AssertionError(f"retired v2/v1 mechanics remain in {name}: {token}")


def _check_coupling_cutover() -> None:
    source = _source("fast_plasma_coupling_diagnostic.py")
    for token in ("fast_plasma_relaxation_v2", "v2."):
        if token in source:
            raise AssertionError(f"coupling diagnostic retained v2 dependency: {token}")
    for token in (
        "from . import artifacts",
        "from . import cases as case_ops",
        "from .runtime import resolve_executable, run_qpx, validate_executable",
        "from .scale_audit import mesh_stats",
        "case_ops.stage_case(",
        "case_ops.validate_case_references(",
        "artifacts.write_json_bundle(",
        "BASE_CASE_RELATIVE = Path(\"tests/Issue2_electron_bulk_drift/qvt_prepoisson\")",
    ):
        if token not in source:
            raise AssertionError(f"coupling canonical cutover drift: {token}")


def _check_inventory_cutover() -> None:
    source = _source("electron_inventory_nullspace.py")
    for token in ("fast_plasma_relaxation_v2", "v2."):
        if token in source:
            raise AssertionError(f"Issue45 inventory retained v2 dependency: {token}")
    for token in (
        "from . import artifacts",
        "from . import cases as case_ops",
        "from .runtime import resolve_executable, run_command, run_qpx, validate_executable",
        "from .scale_audit import mesh_stats",
        "BASE_CASE_RELATIVE = coupling_diag.BASE_CASE_RELATIVE",
        "case_ops.stage_case(",
        "case_ops.validate_case_references(",
        "artifacts.write_json_bundle(",
        "def _write_json(",
        "resolve_executable(",
        "validate_executable(",
        "def _stage_case(",
    ):
        if token not in source:
            raise AssertionError(f"Issue45 canonical cutover drift: {token}")


def _check_first_linear_cutover() -> None:
    source = _source("petsc_first_linear_diagnostic.py")
    for token in ("fast_plasma_relaxation_v2", "v2.", "v2.v1."):
        if token in source:
            raise AssertionError(f"first-linear retained v2 dependency: {token}")
    for token in (
        "from . import artifacts",
        "from .runtime import resolve_executable, run_qpx, validate_executable",
        "inv._stage_case(base_case, case_dir, text)",
        "resolve_executable(",
        "validate_executable(",
        "artifacts.write_json_bundle(",
    ):
        if token not in source:
            raise AssertionError(f"first-linear canonical cutover drift: {token}")


def _check_localization_cutover() -> None:
    source = _source("augmented_jacobian_localization.py")
    for token in ("fast_plasma_relaxation_v2", "v2.", "v2.v1."):
        if token in source:
            raise AssertionError(f"Issue46 localization retained v2 dependency: {token}")
    for token in (
        "from . import artifacts",
        "from .runtime import resolve_executable, run_qpx, validate_executable",
        "inv._stage_case(base_case, main_dir, localization_text)",
        "resolve_executable(",
        "validate_executable(",
        "artifacts.write_json_bundle(",
    ):
        if token not in source:
            raise AssertionError(f"Issue46 localization canonical cutover drift: {token}")


def _check_fd_reference_cutover() -> None:
    source = _source("jacobian_fd_reference_audit.py")
    for token in ("fast_plasma_relaxation_v2", "v2.", "v2.v1."):
        if token in source:
            raise AssertionError(f"Issue46 FD-reference retained v2 dependency: {token}")
    for token in (
        "from . import artifacts",
        "from .runtime import resolve_executable, run_qpx, validate_executable",
        "inv._stage_case(base_case, case_dir, ds_text)",
        "resolve_executable(",
        "validate_executable(",
        "artifacts.write_json_bundle(",
    ):
        if token not in source:
            raise AssertionError(f"Issue46 FD-reference canonical cutover drift: {token}")


def _check_canonical_runtime_owner() -> None:
    source = Path(runtime43.__file__).read_text()
    for forbidden in (
        "fast_plasma_relaxation_v2",
        "fast_plasma_relaxation_v5",
    ):
        if forbidden in source:
            raise AssertionError(f"canonical runtime version dependency leaked: {forbidden}")
    for token in (
        "from recipes import issue43_fast_relaxation as relaxation_recipe",
        "def build_electron_300k(",
        "def build_oneway(",
        "def build_feedback(",
        "def run_qpx_case(",
        "def run_known_good(",
        "def run_case(",
        "def nonlinear_residual_summary(",
        "def attach_nonlinear_residual(",
        "def physics_pass(",
    ):
        if token not in source:
            raise AssertionError(f"canonical Issue43 runtime surface drift: {token}")


def main() -> int:
    try:
        _check_consumer_topology()
        _check_v2_retired()
        _check_remaining_stale_refs()
        _check_coupling_cutover()
        _check_inventory_cutover()
        _check_first_linear_cutover()
        _check_localization_cutover()
        _check_fd_reference_cutover()
        _check_canonical_runtime_owner()
    except Exception as exc:
        print(f"ISSUE48_FAST_PLASMA_V2_DEPENDENCY_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_FAST_PLASMA_V2_DEPENDENCY_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
