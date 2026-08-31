#!/usr/bin/env python3
"""P0 characterization for the Issue31 coupling recipe extraction/cutover."""
from __future__ import annotations

import ast
import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recipes import issue31_coupling as recipe
from qpx_harness import coupling_evr1_safe as safe
from qpx_harness import coupling_evr2_timestep as evr2


EXPECTED_CONSTANTS = {
    "BASE_INPUT_RELATIVE": Path(
        "archive/Issue29_monolithic_performance_bound/monolithic_q0_reference.i"
    ),
    "DEFAULT_ASSET_CASE_RELATIVE": Path(
        "temp/tests/Issue22_qvt_transient_species_accumulation"
    ),
    "SOURCE_RELATIVE": Path("src/materials/QPXThermalDiffusionMaterial.C"),
    "SPECIES": ("O2s", "O2p", "O", "Om", "Op", "Os"),
    "TRANSPORT_REMOVE_PATHS": (
        "Variables/potential_plasma",
        "FVKernels/r30_phi_diffusion",
        "FVKernels/r30_phi_charge_source",
        "FVBCs/r30_phi_plasma_metal",
        "FVBCs/r30_phi_plasma_electrode",
        "FVBCs/r30_phi_plasma_right",
        "FVBCs/r30_phi_inlet",
        "FVBCs/r30_phi_outlet",
        "Postprocessors/r29_phi_min",
        "Postprocessors/r29_phi_max",
        "Postprocessors/r29_phi_integral",
    ),
    "E_CHARGE": 1.602176634e-19,
    "SUM_W_TOL": 1.0e-10,
    "BOUND_TOL": 1.0e-10,
    "CHARGE_REL_TOL": 1.0e-3,
    "PHI_NONTRIVIAL_TOL": 1.0e-14,
}
RETAINED_TRANSPORT_TOKENS = (
    "n_e_solved",
    "r30_e_time",
    "r30_e_diffusion",
    "r30_charge_density",
)
REMOVED_TRANSPORT_TOKENS = (
    "potential_plasma",
    "r30_phi_diffusion",
    "r30_phi_charge_source",
    "r30_phi_plasma_metal",
    "r30_phi_plasma_electrode",
    "r30_phi_plasma_right",
    "r30_phi_inlet",
    "r30_phi_outlet",
    "r29_phi_min",
    "r29_phi_max",
    "r29_phi_integral",
)


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
    for name, expected in EXPECTED_CONSTANTS.items():
        if getattr(recipe, name) != expected:
            raise AssertionError(
                f"Issue31 recipe constant drift: {name}={getattr(recipe, name)!r}"
            )


def _check_transport_transform() -> None:
    transformed, meta = recipe.transport_only_input(_base_input())
    if meta.get("removed_paths") != list(EXPECTED_CONSTANTS["TRANSPORT_REMOVE_PATHS"]):
        raise AssertionError("Issue31 transport removal-path contract drift")
    if meta.get("retained_required_tokens") != list(RETAINED_TRANSPORT_TOKENS):
        raise AssertionError("Issue31 retained transport-token contract drift")
    if len(meta.get("removed_spans", [])) != len(EXPECTED_CONSTANTS["TRANSPORT_REMOVE_PATHS"]):
        raise AssertionError("Issue31 transport removal-span count drift")
    if "[u]" not in transformed:
        raise AssertionError("unrelated variable was removed by transport transform")
    for token in RETAINED_TRANSPORT_TOKENS:
        if token not in transformed:
            raise AssertionError(f"required transport token was removed: {token}")
    for token in REMOVED_TRANSPORT_TOKENS:
        if token in transformed:
            raise AssertionError(f"Poisson token survived transport transform: {token}")

    bad = _base_input().replace("[r29_phi_integral]\n  []\n", "")
    try:
        recipe.transport_only_input(bad)
    except recipe.Issue31CouplingError:
        pass
    else:
        raise AssertionError("missing-block negative control passed")


def _check_csv_selection() -> None:
    row0 = _physics_row(time="0")
    row1 = _physics_row(time="1e-4")
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        _write_csv(root / "input_out_r29_csv.csv", [row0, row1])
        _write_csv(root / "input_out.csv", [row0, row1])
        recipe_path, recipe_row = recipe.physics_csv(root, monolithic=True)
        safe_path, safe_row = safe.physics_csv(root, monolithic=True)
        if recipe_path.name != "input_out.csv" or recipe_row != row1:
            raise AssertionError("canonical solved-time CSV selection contract drift")
        if safe_path != recipe_path or safe_row != recipe_row:
            raise AssertionError("safe adapter CSV-selection contract drift")

    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        _write_csv(root / "named_only.csv", [row1])
        recipe_path, recipe_row = recipe.physics_csv(root, monolithic=True)
        safe_path, safe_row = safe.physics_csv(root, monolithic=True)
        if recipe_path.name != "named_only.csv" or recipe_row != row1:
            raise AssertionError("named-only deterministic CSV fallback drift")
        if safe_path != recipe_path or safe_row != recipe_row:
            raise AssertionError("safe adapter named-only fallback drift")

    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        try:
            recipe.physics_csv(root, monolithic=False)
        except recipe.Issue31CouplingError:
            pass
        else:
            raise AssertionError("missing-CSV recipe negative control passed")

        try:
            safe.physics_csv(root, monolithic=False)
        except safe.CouplingEVR1Error:
            pass
        else:
            raise AssertionError("safe adapter error translation drift")


def _expected_physics(path: Path, *, monolithic: bool) -> dict:
    checks = {
        "electron_nonnegative": True,
        "constrained_sum_unity": True,
    }
    species = {}
    for name in EXPECTED_CONSTANTS["SPECIES"]:
        species[name] = {"min": 0.01, "max": 0.2}
        checks[f"{name}_bounds"] = True
    checks["charge_finite_ordered"] = True
    checks["charge_integral_identity"] = True

    potential = None
    if monolithic:
        potential = {"min": -2.0, "max": 3.0, "integral": 0.5}
        checks["potential_ordered"] = True
        checks["potential_nontrivial"] = True

    return {
        "status": "PASS",
        "csv": str(path),
        "time": 1.0e-4,
        "checks": checks,
        "electron": {"min": 1.0e16, "max": 1.1e16},
        "sum_w": {"min": 1.0, "max": 1.0},
        "species": species,
        "charge": {
            "min": -1.0,
            "max": 1.0,
            "integral": 0.0,
            "expected_integral": 0.0,
            "relative_identity_error": 0.0,
        },
        "potential": potential,
    }


def _check_physics_contract() -> None:
    row = _physics_row()
    with tempfile.TemporaryDirectory() as tmp_name:
        root = Path(tmp_name)
        path = root / "input_out.csv"
        _write_csv(path, [row])
        for monolithic in (False, True):
            actual = recipe.physics_check(root, monolithic=monolithic)
            expected = _expected_physics(path, monolithic=monolithic)
            if actual != expected:
                raise AssertionError(
                    f"Issue31 physics contract drift monolithic={monolithic}: {actual}"
                )

        broken = dict(row)
        broken["r29_sum_w_max"] = "1.1"
        _write_csv(path, [broken])
        actual = recipe.physics_check(root, monolithic=True)
        if actual["status"] != "FAIL" or actual["checks"]["constrained_sum_unity"]:
            raise AssertionError("physics negative control passed")


def _imports_module(path: Path, module: str) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == module for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if base == module:
                return True
            if base == "qpx_harness" and module.startswith("qpx_harness."):
                leaf = module.split(".", 1)[1]
                if any(alias.name == leaf for alias in node.names):
                    return True
    return False


def _check_safe_scoped_patch() -> None:
    base = safe.base
    original_main = base.main
    original_csv = base._physics_csv
    observed: dict[str, bool] = {}

    def fake_main(args) -> int:
        observed["active"] = base._physics_csv is safe.physics_csv
        return 7

    base.main = fake_main
    try:
        rc = safe.main([])
    finally:
        base.main = original_main

    if rc != 7 or not observed.get("active"):
        raise AssertionError("safe adapter did not scope recipe-backed CSV selection")
    if base._physics_csv is not original_csv:
        raise AssertionError("safe adapter did not restore EVR1 CSV selector")


def _check_production_cutover() -> None:
    this_path = Path(__file__)
    if _imports_module(this_path, "qpx_harness.coupling_evr1"):
        raise AssertionError("WP10 retained direct coupling_evr1 oracle import")

    evr2_path = Path(evr2.__file__)
    if _imports_module(evr2_path, "qpx_harness.coupling_evr1"):
        raise AssertionError("EVR2 still imports coupling_evr1")
    if _imports_module(evr2_path, "qpx_harness.coupling_evr1_safe"):
        raise AssertionError("EVR2 still imports coupling_evr1_safe")

    evr2_source = evr2_path.read_text()
    for required in (
        "from recipes import issue31_coupling as recipe",
        "validate_referenced_files",
        "recipe.transport_only_input",
        "recipe.physics_check",
        "recipe.SPECIES",
    ):
        if required not in evr2_source:
            raise AssertionError(f"EVR2 recipe cutover missing: {required}")

    safe_source = Path(safe.__file__).read_text()
    for required in (
        "from recipes import issue31_coupling as recipe",
        "original_physics_csv = base._physics_csv",
        "base._physics_csv = physics_csv",
        "base._physics_csv = original_physics_csv",
    ):
        if required not in safe_source:
            raise AssertionError(f"safe adapter scoped cutover missing: {required}")
    for forbidden in ("def _activate", "base.self_test ="):
        if forbidden in safe_source:
            raise AssertionError(f"safe adapter retained legacy monkey-patch path: {forbidden}")

    _check_safe_scoped_patch()


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
            raise AssertionError(
                f"Issue31 recipe leaked runtime owner semantics: {forbidden}"
            )


def main() -> int:
    try:
        _check_constants()
        _check_transport_transform()
        _check_csv_selection()
        _check_physics_contract()
        _check_production_cutover()
        _check_boundary()
    except Exception as exc:
        print(f"ISSUE48_ISSUE31_COUPLING_RECIPE_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE31_COUPLING_RECIPE_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
