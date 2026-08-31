#!/usr/bin/env python3
"""P0 characterization for the Issue31 coupling recipe extraction."""
from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recipes import issue31_coupling as recipe
from qpx_harness import coupling_evr1 as legacy
from qpx_harness import coupling_evr1_safe as safe


def _base_input() -> str:
    return """
[Variables]
  [u]
  []
  [n_e_solved]
  []
  [potential_plasma]
  []
[]
[FunctorMaterials]
  [r30_charge_density]
  []
[]
[FVKernels]
  [r30_e_time]
  []
  [r30_e_diffusion]
  []
  [r30_phi_diffusion]
  []
  [r30_phi_charge_source]
  []
[]
[FVBCs]
  [r30_phi_plasma_metal]
  []
  [r30_phi_plasma_electrode]
  []
  [r30_phi_plasma_right]
  []
  [r30_phi_inlet]
  []
  [r30_phi_outlet]
  []
[]
[Postprocessors]
  [r29_phi_min]
  []
  [r29_phi_max]
  []
  [r29_phi_integral]
  []
[]
"""


def _physics_row(*, time: str = "1e-4") -> dict[str, str]:
    row = {
        "time": time,
        "r29_ne_min": "1e16",
        "r29_ne_max": "1.1e16",
        "r29_charge_min": "-1",
        "r29_charge_max": "1",
        "r29_charge_integral": "0",
        "r29_heavy_charge_number_integral": "1e16",
        "r29_electron_charge_number_integral": "-1e16",
        "r29_sum_w_min": "1",
        "r29_sum_w_max": "1",
        "r29_phi_min": "-2",
        "r29_phi_max": "3",
        "r29_phi_integral": "0.5",
    }
    for species in recipe.SPECIES:
        row[f"r29_w_{species}_min"] = "0.01"
        row[f"r29_w_{species}_max"] = "0.2"
    return row


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _check_constants() -> None:
    for name in (
        "BASE_INPUT_RELATIVE",
        "DEFAULT_ASSET_CASE_RELATIVE",
        "SOURCE_RELATIVE",
        "SPECIES",
        "TRANSPORT_REMOVE_PATHS",
        "E_CHARGE",
        "SUM_W_TOL",
        "BOUND_TOL",
        "CHARGE_REL_TOL",
        "PHI_NONTRIVIAL_TOL",
    ):
        if getattr(recipe, name) != getattr(legacy, name):
            raise AssertionError(f"Issue31 recipe constant drift: {name}")


def _check_transport_transform() -> None:
    base = _base_input()
    expected_text, expected_meta = legacy.transport_only_input(base)
    actual_text, actual_meta = recipe.transport_only_input(base)
    if actual_text != expected_text or actual_meta != expected_meta:
        raise AssertionError("Issue31 transport-only transform equivalence drift")

    bad = base.replace("[r29_phi_integral]\n  []\n", "")
    legacy_failed = False
    recipe_failed = False
    try:
        legacy.transport_only_input(bad)
    except legacy.CouplingEVR1Error:
        legacy_failed = True
    try:
        recipe.transport_only_input(bad)
    except recipe.Issue31CouplingError:
        recipe_failed = True
    if not legacy_failed or not recipe_failed:
        raise AssertionError("missing-block negative control drift")


def _check_csv_selection() -> None:
    row0 = _physics_row(time="0")
    row1 = _physics_row(time="1e-4")
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        _write_csv(root / "input_out_r29_csv.csv", [row0, row1])
        _write_csv(root / "input_out.csv", [row0, row1])
        expected_path, expected_row = safe.physics_csv(root, monolithic=True)
        actual_path, actual_row = recipe.physics_csv(root, monolithic=True)
        if actual_path != expected_path or actual_row != expected_row:
            raise AssertionError("canonical CSV selection equivalence drift")
        if actual_path.name != "input_out.csv" or actual_row["time"] != "1e-4":
            raise AssertionError("canonical solved-time selection contract drift")

    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        _write_csv(root / "named_only.csv", [row1])
        expected_path, expected_row = safe.physics_csv(root, monolithic=True)
        actual_path, actual_row = recipe.physics_csv(root, monolithic=True)
        if actual_path != expected_path or actual_row != expected_row:
            raise AssertionError("named-only CSV fallback equivalence drift")

    with tempfile.TemporaryDirectory() as tmp_name:
        try:
            recipe.physics_csv(Path(tmp_name), monolithic=False)
        except recipe.Issue31CouplingError:
            pass
        else:
            raise AssertionError("missing-CSV negative control passed")


def _legacy_safe_physics_check(case_dir: Path, *, monolithic: bool) -> dict:
    original = legacy._physics_csv
    legacy._physics_csv = safe.physics_csv
    try:
        return legacy.physics_check(case_dir, monolithic=monolithic)
    finally:
        legacy._physics_csv = original


def _check_physics_equivalence() -> None:
    row = _physics_row()
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        _write_csv(root / "input_out.csv", [row])
        for monolithic in (False, True):
            expected = _legacy_safe_physics_check(root, monolithic=monolithic)
            actual = recipe.physics_check(root, monolithic=monolithic)
            if actual != expected:
                raise AssertionError(
                    f"Issue31 physics-check equivalence drift monolithic={monolithic}"
                )

        broken = dict(row)
        broken["r29_sum_w_max"] = "1.1"
        _write_csv(root / "input_out.csv", [broken])
        actual = recipe.physics_check(root, monolithic=True)
        if actual["status"] != "FAIL" or actual["checks"]["constrained_sum_unity"]:
            raise AssertionError("physics negative control passed")


def _check_boundary() -> None:
    source = Path(recipe.__file__).read_text()
    for forbidden in (
        "coupling_evr1",
        "coupling_evr1_safe",
        "performance_core",
        "performance_smoke",
        "performance_investigation",
        "qpx_harness.runtime",
        "run_measurement",
    ):
        if forbidden in source:
            raise AssertionError(f"Issue31 recipe leaked runtime owner semantics: {forbidden}")


def main() -> int:
    try:
        _check_constants()
        _check_transport_transform()
        _check_csv_selection()
        _check_physics_equivalence()
        _check_boundary()
    except Exception as exc:
        print(f"ISSUE48_ISSUE31_COUPLING_RECIPE_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE31_COUPLING_RECIPE_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
