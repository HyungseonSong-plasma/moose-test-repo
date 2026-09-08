"""QPX-free builders for the R3 electron-density scaling verification."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from experiments.Issue93_r3_electron_isolation.operator_decomposition import build_case_input
from experiments.Issue93_r3_electron_isolation.prepare import ELECTRON_REFERENCE_CASE
from experiments.historical_recipe_support.issue91_r3 import audit_r3_input, build_r3_input
from qpx_harness.adapters.moose import parameters as mp

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
    cancels the constant N_ref from time and diffusion terms. This remains the
    bounded electron-only representation check used by the historical campaign.
    """
    text = build_case_input("C2", electron_reference_case)
    text = mp.upsert_parameter(text, "Variables/n_e", "initial_condition", "1.0")
    # At O(1) state the constant-state residual is expected at floating-point
    # floor. Relative convergence alone can demand an impossible further 1e-8
    # reduction from an O(1e-16) initial residual and trigger line-search failure.
    text = mp.upsert_parameter(text, "Executioner", "nl_abs_tol", "1.0e-14")
    return (
        "# R3 scaling verification N0: n_e is the normalized unknown n_hat.\n"
        "# Physical mapping for this homogeneous E=0 discriminator: n_e_phys=1e16*n_hat.\n"
        + text
    )


def audit_normalized_r3_input(text: str, *, expected_field: float) -> dict[str, Any]:
    """Verify that the canonical Issue91 recipe retains the proven scaling contract."""
    canonical = audit_r3_input(text, expected_field=expected_field)
    checks = dict(canonical["checks"])
    checks["physical_reference_retained"] = f"n_e_value = {N_E_REF:.0e}" in text
    failed = sorted(key for key, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failed else "FAIL",
        "expected_field": expected_field,
        "reference_density_m3": N_E_REF,
        "checks": checks,
        "failed_checks": failed,
    }


def build_normalized_r3_input(base_text: str, *, field_strength: float) -> tuple[str, dict[str, Any]]:
    """Build and verify the now-canonical O(1) Issue91 electron representation.

    The scaling campaign originally applied this transformation after canonical
    R3 construction. After production promotion, ``build_r3_input`` owns the
    normalized solver unknown and physical-density bridge. This wrapper must
    therefore verify, not apply, the transformation a second time.
    """
    text, canonical_meta = build_r3_input(base_text, field_strength=field_strength)
    audit = audit_normalized_r3_input(text, expected_field=field_strength)
    if audit["status"] != "PASS":
        raise ScalingCounterfactualError(
            f"canonical normalized R3 failed scaling audit: {audit['failed_checks']}"
        )
    meta = {
        **canonical_meta,
        "canonical_audit": canonical_meta.get("audit"),
        "counterfactual": "CANONICAL_ELECTRON_DENSITY_O1_REPRESENTATION_VERIFICATION",
        "reference_density_m3": canonical_meta["electron_reference_density_m3"],
        "solver_unknown": canonical_meta["electron_solver_unknown"],
        "physical_density_functor": canonical_meta["electron_physical_density"],
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
            "bounded verification only supports E0=0 or E0=0.01 V/m"
        )
    source = R3_E0_DIR if field_strength == 0.0 else R3_ECONST_DIR
    _copy_case_tree(source, target)
    base = (source / "heavy_base.i").read_text()
    text, meta = build_normalized_r3_input(base, field_strength=field_strength)
    (target / "input.i").write_text(text)
    return meta
