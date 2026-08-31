#!/usr/bin/env python3
"""P0 characterization for fast_plasma_relaxation_v2 dependency retirement.

This checkpoint is intentionally observational: it freezes the current consumer
surface before migrating each runtime owner away from the historical v2 layer.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import fast_plasma_relaxation_v2 as v2


EXPECTED_RUNTIME_CONSUMERS = {
    "augmented_jacobian_localization.py",
    "electron_inventory_nullspace.py",
    "fast_plasma_coupling_diagnostic.py",
    "fast_plasma_relaxation_v5.py",
    "jacobian_fd_reference_audit.py",
    "petsc_first_linear_diagnostic.py",
}


def _source(path: Path) -> str:
    return path.read_text()


def _observed_consumers() -> dict[str, str]:
    result: dict[str, str] = {}
    pattern = re.compile(
        r"from \. import fast_plasma_relaxation_v2 as v2|"
        r"import qpx_harness\.fast_plasma_relaxation_v2 as v2"
    )
    for path in (ROOT / "qpx_harness").glob("*.py"):
        if path.name == "fast_plasma_relaxation_v2.py":
            continue
        text = _source(path)
        if pattern.search(text):
            result[path.name] = text
    return result


def _check_consumer_topology() -> None:
    observed = _observed_consumers()
    if set(observed) != EXPECTED_RUNTIME_CONSUMERS:
        raise AssertionError(
            "v2 runtime consumer topology drift: "
            f"observed={sorted(observed)} expected={sorted(EXPECTED_RUNTIME_CONSUMERS)}"
        )

    v5 = observed["fast_plasma_relaxation_v5.py"]
    for required in (
        "_RAW_BUILD_ELECTRON_300K = v2._build_electron_300k",
        "_RAW_BUILD_ONEWAY = v2._build_oneway",
        "_RAW_BUILD_FEEDBACK = v2._build_feedback",
        "_RAW_RUN_CASE = v2._run_case",
    ):
        if required not in v5:
            raise AssertionError(f"v5 genuine v2 dependency drift: {required}")


def _check_historical_v1_boundary() -> None:
    source = Path(v2.__file__).read_text()
    if "from . import fast_plasma_relaxation as v1" in source:
        raise AssertionError("v2 reintroduced the retired historical v1 module")

    if not hasattr(v2.v1, "FastPlasmaRelaxationError"):
        raise AssertionError("v2 error compatibility alias is missing")
    for forbidden_attr in ("BASE_CASE_RELATIVE", "_copy_case", "_validate_assets"):
        if hasattr(v2.v1, forbidden_attr):
            raise AssertionError(
                f"v2 unexpectedly reintroduced retired v1 runtime surface: {forbidden_attr}"
            )


def _check_stale_compatibility_references() -> None:
    observed = _observed_consumers()
    stale: dict[str, set[str]] = {}
    pattern = re.compile(r"\bv2\.v1\.([A-Za-z_]\w*)")
    for name, source in observed.items():
        refs = set(pattern.findall(source))
        if refs:
            stale[name] = refs

    required_attrs = {"BASE_CASE_RELATIVE", "_copy_case", "_validate_assets"}
    union = set().union(*stale.values()) if stale else set()
    if not required_attrs.issubset(union):
        raise AssertionError(
            f"expected stale v1 compatibility references changed: {sorted(union)}"
        )

    required_consumers = {
        "electron_inventory_nullspace.py",
        "fast_plasma_coupling_diagnostic.py",
        "petsc_first_linear_diagnostic.py",
    }
    if not required_consumers.issubset(stale):
        raise AssertionError(
            "expected stale v1 runtime consumers changed: "
            f"observed={sorted(stale)}"
        )


def _check_v2_mixed_owner_surface() -> None:
    source = Path(v2.__file__).read_text()
    for required in (
        "def _stage_case(",
        "def _validate_assets(",
        "def _write_json(",
        "def _build_electron_300k(",
        "def _build_oneway(",
        "def _build_feedback(",
        "def _run_case(",
        "def classify(",
    ):
        if required not in source:
            raise AssertionError(f"v2 mixed-owner surface drift: {required}")

    for canonical in (
        "from recipes import issue43_fast_relaxation as relaxation_recipe",
        "from . import cases as case_ops",
        "from .runtime import resolve_executable, run_qpx, validate_executable",
    ):
        if canonical not in source:
            raise AssertionError(f"v2 canonical dependency drift: {canonical}")


def main() -> int:
    try:
        _check_consumer_topology()
        _check_historical_v1_boundary()
        _check_stale_compatibility_references()
        _check_v2_mixed_owner_surface()
    except Exception as exc:
        print(f"ISSUE48_FAST_PLASMA_V2_DEPENDENCY_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_FAST_PLASMA_V2_DEPENDENCY_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
