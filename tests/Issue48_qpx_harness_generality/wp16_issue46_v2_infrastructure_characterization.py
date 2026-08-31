#!/usr/bin/env python3
"""P0 characterization for retired Issue46 dependencies on fast_plasma_relaxation_v2."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import artifacts
from qpx_harness import electron_inventory_nullspace as inv
from qpx_harness import runtime

ISSUE46_CUTOVERS = {
    "augmented_jacobian_localization.py": "inv._stage_case(base_case, main_dir, localization_text)",
    "jacobian_fd_reference_audit.py": "inv._stage_case(base_case, case_dir, ds_text)",
}

FORBIDDEN_V2_MODEL_RUNTIME_TOKENS = (
    "v2._build_electron_300k(",
    "v2._build_oneway(",
    "v2._build_feedback(",
    "v2._run_case(",
    "v2.classify(",
)


def _source(name: str) -> str:
    return (ROOT / "qpx_harness" / name).read_text()


def _check_issue46_cutovers() -> None:
    for name, stage_token in ISSUE46_CUTOVERS.items():
        source = _source(name)
        for token in ("fast_plasma_relaxation_v2", "v2.", "v2.v1."):
            if token in source:
                raise AssertionError(f"Issue46 owner retained v2 dependency in {name}: {token}")
        for token in (
            "from . import artifacts",
            "from .runtime import resolve_executable, run_qpx, validate_executable",
            stage_token,
            "artifacts.write_json_bundle(",
            "resolve_executable(",
            "validate_executable(",
        ):
            if token not in source:
                raise AssertionError(f"Issue46 canonical cutover drift in {name}: {token}")
        for token in FORBIDDEN_V2_MODEL_RUNTIME_TOKENS:
            if token in source:
                raise AssertionError(f"Issue46 unexpectedly depends on v2 model/runtime core in {name}: {token}")


def _check_canonical_destination_readiness() -> None:
    if not callable(getattr(inv, "_stage_case", None)):
        raise AssertionError("inventory construction owner lacks canonical _stage_case")
    if not callable(getattr(runtime, "resolve_executable", None)):
        raise AssertionError("runtime.resolve_executable missing")
    if not callable(getattr(runtime, "validate_executable", None)):
        raise AssertionError("runtime.validate_executable missing")
    if not callable(getattr(artifacts, "write_json_bundle", None)):
        raise AssertionError("artifacts.write_json_bundle missing")


def _check_already_cut_consumers() -> None:
    for name in (
        "electron_inventory_nullspace.py",
        "fast_plasma_coupling_diagnostic.py",
        "petsc_first_linear_diagnostic.py",
    ):
        source = _source(name)
        if "fast_plasma_relaxation_v2" in source or "v2." in source:
            raise AssertionError(f"already-cut consumer regressed to v2: {name}")


def main() -> int:
    try:
        _check_issue46_cutovers()
        _check_canonical_destination_readiness()
        _check_already_cut_consumers()
    except Exception as exc:
        print(f"ISSUE48_ISSUE46_V2_INFRA_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE46_V2_INFRA_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
