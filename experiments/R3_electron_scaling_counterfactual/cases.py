"""QPX-free builders for the R3 electron-density scaling counterfactual."""
from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path
from typing import Any

from experiments.Issue93_r3_electron_isolation.operator_decomposition import build_case_input
from experiments.Issue93_r3_electron_isolation.prepare import ELECTRON_REFERENCE_CASE
from recipes.issue91_r3 import build_r3_input
from qpx_harness.moose import blocks as mb
from qpx_harness.moose import parameters as mp

ROOT = Path(__file__).resolve().parents[2]
N_E_REF = 1.0e16
R3_E0_DIR = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"
R3_ECONST_DIR = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_econst"


class ScalingCounterfactualError(RuntimeError):
    pass


def build_normalized_electron_input(
    electron_reference_case: Path = ELECTRON_REFERENCE_CASE,
) -> str:
    """Return the zero-field time+diffusion case with an O(1) solver unknown.

    The source equation is homogeneous and linear in n_e, so n_e=N_ref*n_hat
    cancels the constant N_ref from time and diffusion terms. This is therefore
    a physics-equivalent representation for the electron-only E=0 discriminator.
    """
    text = build_case_input("C2", electron_reference_case)
    text = mp.upsert_parameter(text, "Variables/n_e", "initial_condition", "1.0")
    # At O(1) state the constant-state residual is expected at floating-point
    # floor. Relative convergence alone can demand an impossible further 1e-8
    # reduction from an O(1e-16) initial residual and trigger line-search failure.
    text = mp.upsert_parameter(text, "Executioner", "nl_abs_tol", "1.0e-14")
    return (
        "# R3 scaling counterfactual N0: n_e is the normalized unknown n_hat.\n"
        "# Physical mapping for this homogeneous E=0 discriminator: n_e_phys=1e16*n_hat.\n"
        + text
    )


def _insert_physical_density_bridge(text: str) -> str:
    mb.require_absent(text, "FunctorMaterials/electron_density_physical")
    return mb.insert_child_block(
        text,
        "FunctorMaterials",
        """  [electron_density_physical]
    type = ADParsedFunctorMaterial
    property_name = n_e_physical
    functor_names = 'n_e'
    functor_symbols = 'ne_hat'
    expression = '${n_e_value}*ne_hat'
    block = plasma
  []""",
    )


def audit_normalized_r3_input(text: str, *, expected_field: float) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    checks["normalized_solver_ic"] = (
        mp.get_parameter(text, "Variables/n_e", "initial_condition") == "1.0"
    )
    checks["physical_bridge_present"] = mb.has_block(
        text, "FunctorMaterials/electron_density_physical"
    )
    state_names = mp.words(
        mp.get_parameter(text, "FunctorMaterials/state_constants", "prop_names")
    )
    checks["no_competing_constant_n_e_provider"] = "n_e" not in state_names
    checks["physical_bridge_expression"] = (
        mp.get_parameter(
            text,
            "FunctorMaterials/electron_density_physical",
            "expression",
        )
        == "'${n_e_value}*ne_hat'"
    )
    checks["heavy_uses_physical_density"] = (
        mp.get_parameter(
            text,
            "FunctorMaterials/heavy_transport",
            "electron_number_density",
        )
        == "n_e_physical"
    )
    for kernel in ("n_e_time", "n_e_diffusion", "n_e_drift"):
        checks[f"solver_kernel:{kernel}"] = (
            mp.get_parameter(text, f"FVKernels/{kernel}", "variable") == "n_e"
        )
    for postprocessor in ("n_e_avg", "n_e_min", "n_e_max", "n_e_inventory"):
        checks[f"physical_output:{postprocessor}"] = (
            mp.get_parameter(text, f"Postprocessors/{postprocessor}", "functor")
            == "n_e_physical"
        )
    checks["physical_reference_retained"] = f"n_e_value = {N_E_REF:.0e}" in text
    field_match = re.search(r"(?m)^\s*E0_migration\s*=\s*([^#\r\n]+)", text)
    checks["field_strength"] = bool(
        field_match
        and math.isclose(
            float(field_match.group(1).strip()),
            expected_field,
            rel_tol=0.0,
            abs_tol=1.0e-18,
        )
    )
    checks["field_is_prescribed"] = "potential = phi_prescribed" in text
    checks["poisson_absent"] = not any(
        token in text
        for token in ("potential_plasma", "r30_phi_diffusion", "r30_phi_charge_source")
    )
    failed = sorted(key for key, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failed else "FAIL",
        "expected_field": expected_field,
        "reference_density_m3": N_E_REF,
        "checks": checks,
        "failed_checks": failed,
    }


def build_normalized_r3_input(base_text: str, *, field_strength: float) -> tuple[str, dict[str, Any]]:
    """Build canonical R3 and then change only the electron solver representation.

    The solver variable named ``n_e`` becomes the normalized unknown n_hat~O(1).
    A derived ``n_e_physical = N_ref*n_e`` functor is supplied everywhere the
    heavy model or physical acceptance outputs require dimensional density.
    """
    text, canonical_meta = build_r3_input(base_text, field_strength=field_strength)
    text = mp.upsert_parameter(text, "Variables/n_e", "initial_condition", "1.0")
    text = _insert_physical_density_bridge(text)
    text = mp.upsert_parameter(
        text,
        "FunctorMaterials/heavy_transport",
        "electron_number_density",
        "n_e_physical",
    )
    for postprocessor in ("n_e_avg", "n_e_min", "n_e_max", "n_e_inventory"):
        text = mp.upsert_parameter(
            text,
            f"Postprocessors/{postprocessor}",
            "functor",
            "n_e_physical",
        )
    audit = audit_normalized_r3_input(text, expected_field=field_strength)
    if audit["status"] != "PASS":
        raise ScalingCounterfactualError(
            f"normalized R3 construction failed audit: {audit['failed_checks']}"
        )
    meta = {
        **canonical_meta,
        "canonical_audit": canonical_meta.get("audit"),
        "counterfactual": "ELECTRON_DENSITY_O1_SOLVER_REPRESENTATION",
        "electron_initial_condition": "normalized_1.0",
        "reference_density_m3": N_E_REF,
        "solver_unknown": "n_e == n_hat",
        "physical_density_functor": "n_e_physical == n_e_value*n_e",
        "canonical_physics_checker_preserved": True,
        "audit": audit,
    }
    return text, meta


def _copy_case_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    for pattern in ("input_out*", "*.log", "*.csv", "*.e", "*.exo"):
        for path in target.glob(pattern):
            if path.is_file():
                path.unlink()
    for dirname in (".jitcache", "checkpoint", "checkpoints"):
        path = target / dirname
        if path.is_dir():
            shutil.rmtree(path)


def stage_n0(target: Path, *, electron_reference_case: Path = ELECTRON_REFERENCE_CASE) -> dict[str, Any]:
    _copy_case_tree(electron_reference_case, target)
    text = build_normalized_electron_input(electron_reference_case)
    (target / "input.i").write_text(text)
    expected_path = target / "expected.json"
    expected = json.loads(expected_path.read_text())
    expected["n0"] = 1.0
    expected_path.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
    return {
        "case_id": "N0",
        "meaning": "normalized electron-only E=0 time+diffusion",
        "reference_density_m3": N_E_REF,
        "solver_initial_value": 1.0,
    }


def stage_r3_case(target: Path, *, field_strength: float) -> dict[str, Any]:
    if field_strength not in (0.0, 0.01):
        raise ScalingCounterfactualError(
            "bounded counterfactual only supports E0=0 or E0=0.01 V/m"
        )
    source = R3_E0_DIR if field_strength == 0.0 else R3_ECONST_DIR
    _copy_case_tree(source, target)
    base = (source / "heavy_base.i").read_text()
    text, meta = build_normalized_r3_input(base, field_strength=field_strength)
    (target / "input.i").write_text(text)
    return meta
