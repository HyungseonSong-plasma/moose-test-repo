#!/usr/bin/env python3
"""P0 characterization for fast_plasma_relaxation_v2 dependency retirement."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import fast_plasma_relaxation_v2 as v2

EXPECTED_RUNTIME_CONSUMERS = {
    "augmented_jacobian_localization.py",
    "electron_inventory_nullspace.py",
    "fast_plasma_relaxation_v5.py",
    "jacobian_fd_reference_audit.py",
    "petsc_first_linear_diagnostic.py",
}


def _source(name: str) -> str:
    return (ROOT / "qpx_harness" / name).read_text()


def _observed_consumers() -> dict[str, str]:
    result: dict[str, str] = {}
    tokens = (
        "from . import fast_plasma_relaxation_v2 as v2",
        "import qpx_harness.fast_plasma_relaxation_v2 as v2",
    )
    for path in (ROOT / "qpx_harness").glob("*.py"):
        if path.name == "fast_plasma_relaxation_v2.py":
            continue
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
    v5 = observed["fast_plasma_relaxation_v5.py"]
    for token in (
        "_RAW_BUILD_ELECTRON_300K = v2._build_electron_300k",
        "_RAW_BUILD_ONEWAY = v2._build_oneway",
        "_RAW_BUILD_FEEDBACK = v2._build_feedback",
        "_RAW_RUN_CASE = v2._run_case",
    ):
        if token not in v5:
            raise AssertionError(f"v5 genuine v2 dependency drift: {token}")


def _check_historical_v1_boundary() -> None:
    source = Path(v2.__file__).read_text()
    if "from . import fast_plasma_relaxation as v1" in source:
        raise AssertionError("v2 reintroduced retired v1 module")
    if not hasattr(v2.v1, "FastPlasmaRelaxationError"):
        raise AssertionError("v2 error compatibility alias missing")
    for name in ("BASE_CASE_RELATIVE", "_copy_case", "_validate_assets"):
        if hasattr(v2.v1, name):
            raise AssertionError(f"retired v1 runtime surface returned: {name}")


def _check_remaining_stale_refs() -> None:
    for name in ("electron_inventory_nullspace.py", "petsc_first_linear_diagnostic.py"):
        source = _source(name)
        if "v2.v1." not in source:
            raise AssertionError(f"expected remaining stale v1 reference changed: {name}")
    if "v2.v1." in _source("fast_plasma_coupling_diagnostic.py"):
        raise AssertionError("coupling diagnostic retained stale v1 mechanics")


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


def _check_v2_mixed_owner_surface() -> None:
    source = Path(v2.__file__).read_text()
    for token in (
        "def _stage_case(",
        "def _validate_assets(",
        "def _write_json(",
        "def _build_electron_300k(",
        "def _build_oneway(",
        "def _build_feedback(",
        "def _run_case(",
        "def classify(",
    ):
        if token not in source:
            raise AssertionError(f"v2 mixed-owner surface drift: {token}")


def main() -> int:
    try:
        _check_consumer_topology()
        _check_historical_v1_boundary()
        _check_remaining_stale_refs()
        _check_coupling_cutover()
        _check_v2_mixed_owner_surface()
    except Exception as exc:
        print(f"ISSUE48_FAST_PLASMA_V2_DEPENDENCY_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_FAST_PLASMA_V2_DEPENDENCY_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
