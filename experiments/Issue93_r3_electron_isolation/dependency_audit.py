#!/usr/bin/env python3
"""Issue #93 J0 qpx-free electron residual dependency/ownership audit."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from experiments.historical_recipe_support.issue91_r3 import build_r3_input

ROOT = Path(__file__).resolve().parents[2]
SOURCE_CASE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"


class AuditError(RuntimeError):
    pass


def _require(text: str, snippet: str, claim: str) -> None:
    if snippet not in text:
        raise AuditError(f"contract mismatch for {claim}: missing {snippet!r}")


def _top_level_number(text: str, name: str) -> float:
    match = re.search(rf"(?m)^{re.escape(name)}\s*=\s*([^#\s]+)", text)
    if not match:
        raise AuditError(f"missing top-level assignment: {name}")
    return float(match.group(1))


def audit(source_case: Path = SOURCE_CASE) -> dict[str, Any]:
    heavy_path = source_case / "heavy_base.i"
    if not heavy_path.is_file():
        raise AuditError(f"missing heavy base: {heavy_path}")
    heavy = heavy_path.read_text()
    canonical, _meta = build_r3_input(heavy, field_strength=0.0)

    electron_checks = {
        "n_e_time": ("[n_e_time]", "type = FVTimeKernel", "variable = n_e"),
        "n_e_diffusion": (
            "[n_e_diffusion]",
            "type = FVDiffusion",
            "variable = n_e",
            "coeff = electron_diffusion",
        ),
        "n_e_drift": (
            "[n_e_drift]",
            "type = QPXFVElectrostaticDrift",
            "variable = n_e",
            "carrier = carrier_one",
            "charge_number = -1",
            "mobility = electron_mobility",
            "potential = phi_prescribed",
            "advected_interp_method = upwind",
        ),
        "electron_constants": (
            "[electron_constants]",
            "type = ADGenericFunctorMaterial",
            "prop_names = 'mean_en carrier_one'",
        ),
        "electron_transport": (
            "[electron_transport]",
            "type = QPXElectronTransportLookupMaterial",
            "property_table_file = electron_moments.txt",
            "mean_energy = mean_en",
            "pressure = p",
            "gas_temperature = T_g",
            "bounds_policy = error",
        ),
    }
    for owner, snippets in electron_checks.items():
        for snippet in snippets:
            _require(canonical, snippet, f"{owner}:{snippet}")

    # p is nonlinear; T_g remains a constant functor in state_constants after
    # Issue91 removes only n_e from the old heavy constant bundle.
    _require(canonical, "[p]\n    type = INSFVPressureVariable", "p nonlinear ownership")
    functors = _top_level_block(canonical, "FunctorMaterials")
    _require(functors, "[state_constants]", "state_constants ownership")
    _require(functors, "prop_names = 'T_g T_e mu_flow'", "T_g constant-functor ownership")
    if abs(_top_level_number(canonical, "E0_migration")) > 1.0e-18:
        raise AuditError("R3-E0 canonical field is not zero")

    _require(heavy, "type = QPXThermalDiffusionMaterial", "heavy transport material")
    _require(heavy, "electron_number_density = n_e", "heavy material electron dependency")
    reciprocal: list[dict[str, str]] = []
    species_labels = {
        "w_O2s": "O2s",
        "w_O2p": "O2p",
        "w_O": "O",
        "w_Om": "Om",
        "w_Op": "Op",
        "w_Os": "Os",
    }
    for variable, label in species_labels.items():
        _require(heavy, f"[{label}_diffusion]", f"heavy diffusion owner {variable}")
        _require(heavy, f"diffusivity = D_mix_{label}", f"heavy D_mix consumer {variable}")
        reciprocal.append(
            {
                "residual_variable": variable,
                "kernel": f"{label}_diffusion",
                "material_path": f"n_e -> QPXThermalDiffusionMaterial -> D_mix_{label}",
                "expected_block": f"dR_{variable}/dn_e structurally nonzero in combined R3",
            }
        )

    explicit_electron_fvbc = "variable = n_e" in _top_level_block(canonical, "FVBCs")

    return {
        "issue": 93,
        "audit": "J0_ELECTRON_RESIDUAL_OWNERSHIP",
        "qpx_executed": False,
        "scientific_evr_consumed": 0,
        "source_case": str(source_case),
        "electron_residual_owners": [
            {"object": "n_e_time", "type": "FVTimeKernel", "variable": "n_e"},
            {
                "object": "n_e_diffusion",
                "type": "FVDiffusion",
                "variable": "n_e",
                "coefficient": "electron_diffusion",
            },
            {
                "object": "n_e_drift",
                "type": "QPXFVElectrostaticDrift",
                "variable": "n_e",
                "carrier": "carrier_one",
                "mobility": "electron_mobility",
                "potential": "phi_prescribed",
            },
        ],
        "electron_lookup": {
            "owner": "QPXElectronTransportLookupMaterial",
            "table": "electron_moments.txt",
            "mean_energy": "mean_en",
            "pressure": "p",
            "gas_temperature": "T_g",
            "bounds_policy": "error",
        },
        "coefficient_ownership": {
            "p": "NONLINEAR_INSFV_PRESSURE_VARIABLE",
            "T_g": "CONSTANT_AD_FUNCTOR_MATERIAL_PROPERTY",
            "phi_prescribed": "PRESCRIBED_FUNCTION",
        },
        "newton_dependency_classification": {
            "dR_e_dn_e": "NONZERO_SELF_BLOCK",
            "dR_e_dp": (
                "STRUCTURAL_NONLINEAR_CROSS_BLOCK_VIA_LOOKUP; may evaluate to zero at the "
                "uniform E=0 null-flux state"
            ),
            "dR_e_dT_g": (
                "NO_NEWTON_BLOCK_T_g_IS_CONSTANT_FUNCTOR; coefficient dependency exists but "
                "T_g is not a nonlinear unknown in current R3"
            ),
            "dR_e_dphi": "NO_NEWTON_BLOCK_PHI_IS_PRESCRIBED_FUNCTION",
            "dR_e_du_v_species": "NO_DIRECT_DEPENDENCY",
        },
        "r3_e0_state_specific_zero_paths": {
            "drift": "E=-grad(phi_prescribed)=0, so n_e drift residual is zero",
            "uniform_diffusion": (
                "initial n_e is uniform, so grad(n_e)=0 and diffusion flux is zero even though "
                "D_e structurally depends on p"
            ),
            "source": "no electron source kernel is inserted by the R3 recipe",
        },
        "explicit_electron_fvbc_objects_present": explicit_electron_fvbc,
        "electron_bc_interpretation": (
            "Issue91 inserts no explicit electron FVBC object; J1 preserves that input contract "
            "and leaves framework-effective face behavior to P2/P3 validation"
        ),
        "reciprocal_heavy_dependencies": reciprocal,
        "j1_prediction": (
            "With p and T_g frozen and E=0, the retained accepted electron residual is linear in "
            "n_e. The uniform source-free state is a null-flux invariant subject to the actual "
            "framework-effective FV boundary/runtime semantics."
        ),
        "status": "J0_COMPLETE",
    }


def _top_level_block(text: str, name: str) -> str:
    lines = text.splitlines()
    collecting = False
    depth = 0
    out: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not collecting:
            if stripped == f"[{name}]":
                collecting = True
                depth = 1
                out.append(raw)
            continue
        out.append(raw)
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped == "[]":
                depth -= 1
                if depth == 0:
                    return "\n".join(out)
            else:
                depth += 1
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-case", type=Path, default=SOURCE_CASE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = audit(args.source_case.resolve())
    except (AuditError, OSError, ValueError) as exc:
        print(f"ISSUE93_J0_ERROR: {exc}")
        return 2
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n")
    print(text)
    print("ISSUE93_J0_STATUS: J0_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
