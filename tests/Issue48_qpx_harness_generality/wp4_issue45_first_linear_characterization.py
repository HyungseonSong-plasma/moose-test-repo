#!/usr/bin/env python3
"""P0 characterization for Issue45 first-linear recipe migration."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import electron_inventory_nullspace as inv
from qpx_harness import petsc_first_linear_diagnostic as legacy
from recipes import issue45_first_linear as recipe


def _assert_equal(label: str, new: object, old: object) -> None:
    if new != old:
        raise AssertionError(f"{label} drift:\nnew={new!r}\nold={old!r}")


def _check_construction() -> None:
    base = inv._synthetic_constrained_input(recipe.TARGET)
    old_text, old_meta = legacy.instrument_first_linear(base)
    new_text, new_meta = recipe.instrument_first_linear(base)
    _assert_equal("first-linear input", new_text, old_text)
    _assert_equal("first-linear metadata", new_meta, old_meta)


def _check_analysis_positive() -> None:
    text = legacy._synthetic_log()
    old = legacy.analyze_first_linear_text(text, returncode=1)
    new = recipe.analyze_first_linear_text(text, returncode=1)
    _assert_equal("positive first-linear analysis", new, old)
    if new.get("class") != "GMRES_RESTART_BREAKDOWN":
        raise AssertionError("positive first-linear class drifted")


def _check_analysis_negative_controls() -> None:
    cases: dict[str, str] = {}
    cases["jacobian-mismatch"] = legacy._synthetic_log(1.0e-3)
    cases["pc-failure"] = legacy._synthetic_log().replace(
        "Linear solve did not converge due to DIVERGED_BREAKDOWN iterations 30",
        "Linear solve did not converge due to DIVERGED_PC_FAILED iterations 0\n"
        "PC failed due to FACTOR_NUMERIC_ZEROPIVOT",
        1,
    )
    cases["nonfinite"] = legacy._synthetic_log().replace(
        "n_e:                  5.0e-16",
        "n_e:                  nan",
        1,
    )
    cases["missing-ksp-view"] = legacy._synthetic_log().split("KSP Object:", 1)[0]
    cases["restart-misaligned"] = legacy._synthetic_log().replace(
        "DIVERGED_BREAKDOWN iterations 30",
        "DIVERGED_BREAKDOWN iterations 29",
        1,
    )
    cases["linear-converged"] = legacy._synthetic_log().replace(
        "Linear solve did not converge due to DIVERGED_BREAKDOWN iterations 30",
        "Linear solve converged due to CONVERGED_RTOL iterations 17",
        1,
    )

    for name, text in cases.items():
        old = legacy.analyze_first_linear_text(text, returncode=1)
        new = recipe.analyze_first_linear_text(text, returncode=1)
        _assert_equal(name, new, old)


def _check_primitive_usage() -> None:
    source = (ROOT / "recipes" / "issue45_first_linear.py").read_text()
    required = (
        "from qpx_harness.moose import log as moose_log",
        "from qpx_harness.moose import parameters as mp",
        "from qpx_harness.petsc import jacobian as jac",
        "from qpx_harness.petsc import ksp",
        "from qpx_harness.petsc import log as petsc_log",
        "from qpx_harness.petsc import options as po",
    )
    for token in required:
        if token not in source:
            raise AssertionError(f"recipe does not use expected generic primitive: {token}")

    forbidden = (
        "electron_inventory_nullspace",
        "petsc_first_linear_diagnostic",
        "fast_plasma_coupling_diagnostic",
        "augmented_jacobian_localization",
        "jacobian_fd_reference_audit",
    )
    for token in forbidden:
        if token in source:
            raise AssertionError(f"reverse dependency leaked into Issue45 recipe: {token}")


def main() -> int:
    try:
        _check_construction()
        print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHECK: construction=PASS")
        _check_analysis_positive()
        print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHECK: positive-analysis=PASS")
        _check_analysis_negative_controls()
        print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHECK: negative-controls=PASS")
        _check_primitive_usage()
        print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHECK: recipe-reverse-dependency=NONE")
    except Exception as exc:
        print(f"ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP4_ISSUE45_FIRST_LINEAR_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
