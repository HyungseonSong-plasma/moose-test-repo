#!/usr/bin/env python3
"""Issue #93 J0 qpx-free electron residual dependency/ownership audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from recipes.issue91_r3 import build_r3_input

ROOT = Path(__file__).resolve().parents[2]
SOURCE_CASE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"
HEAVY_SPECIES = ("w_O2s", "w_O2p", "w_O", "w_Om", "w_Op", "w_Os")


class AuditError(RuntimeError):
    pass


def _require(text: str, snippet: str, claim: str) -> None:
    if snippet not in text:
        raise AuditError(f"contract mismatch for {claim}: missing {snippet!r}")


def audit(source_case: Path = SOURCE_CASE) -> dict[str, Any]:
    heavy_path = source_case / "heavy_base.i"
    if not heavy_path.is_file():
        raise AuditError(f"missing heavy base: {heavy_path}")
    heavy = heavy_path.read_text()
    canonical, _meta = build_r3_input(heavy, field_strength=0.0)

    # Electron residual owners inserted by the accepted Issue91 composition policy.
    electron_checks = {
        "electron_time": (
            "type = FVTimeKernel",
            "variable = n_e",
        ),
        "electron_diffusion": (
            "type = FVDiffusion",
            "variable = n_e",
            "coeff = electron_diffusion",
        ),
        "electron_drift": (
            "type = QPXFVElectrostaticDrift",
            "variable = n_e",
            "carrier_number_density = n_e",
            "charge_number = -1",
            "mobility = electron_mobility",
            "potential = phi_prescribed",
        ),
        "electron_transport": (
            "type = QPXElectronTransportLookupMaterial",
            "pressure = p",
            "gas_temperature = T_g",
            "mobility_name = electron_mobility",
            "diffusion_name = electron_diffusion",
        ),
    }
    for owner, snippets in electron_checks.items():
        for snippet in snippets:
            _require(canonical, snippet, f"{owner}:{snippet}")

    # Ownership/classification facts that determine Newton cross blocks.
    _require(canonical, "[p]\n    type = INSFVPressureVariable", "p nonlinear ownership")
    _require(canonical, "[T_g]", "T_g presence")
    _require(canonical, "[AuxVariables]", "T_g auxiliary ownership")
    _require(canonical, "expression = '-0.0*x'", "R3-E0 prescribed zero field")

    # Reciprocal heavy dependency on n_e and its six solved diffusion residuals.
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
        block = f"[{label}_diffusion]"
        diffusivity = f"diffusivity = D_mix_{label}"
        _require(heavy, block, f"heavy diffusion owner {variable}")
        _require(heavy, f"variable = {variable}", f"heavy diffusion variable {variable}")
        _require(heavy, diffusivity, f"heavy D_mix consumer {variable}")
        reciprocal.append(
            {
                "residual_variable": variable,
                "kernel": f"{label}_diffusion",
                "material_path": f"n_e -> QPXThermalDiffusionMaterial -> D_mix_{label}",
                "expected_block": f"dR_{variable}/dn_e structurally nonzero in combined R3",
            }
        )

    # No explicit electron FVBC object is added by Issue91 composition. This does
    # not assert a physics BC beyond the framework-effective default face behavior.
    explicit_electron_fvbc = "variable = n_e" in _top_level_block(canonical, "FVBCs")

    report = {
        "issue": 93,
        "audit": "J0_ELECTRON_RESIDUAL_OWNERSHIP",
        "qpx_executed": False,
        "scientific_evr_consumed": 0,
        "source_case": str(source_case),
        "electron_residual_owners": [
            {"object": "electron_time", "type": "FVTimeKernel", "variable": "n_e"},
            {
                "object": "electron_diffusion",
                "type": "FVDiffusion",
                "variable": "n_e",
                "coefficient": "electron_diffusion",
            },
            {
                "object": "electron_drift",
                "type": "QPXFVElectrostaticDrift",
                "variable": "n_e",
                "mobility": "electron_mobility",
                "potential": "phi_prescribed",
            },
        ],
        "electron_lookup": {
            "owner": "QPXElectronTransportLookupMaterial",
            "pressure": "p",
            "gas_temperature": "T_g",
            "mobility": "electron_mobility",
            "diffusion": "electron_diffusion",
        },
        "newton_dependency_classification": {
            "dR_e_dn_e": "NONZERO_SELF_BLOCK",
            "dR_e_dp": (
                "STRUCTURAL_NONLINEAR_CROSS_BLOCK_VIA_LOOKUP; "
                "may evaluate to zero at the uniform E=0 null-flux state"
            ),
            "dR_e_dT_g": "NO_NEWTON_BLOCK_T_g_IS_AUXILIARY; coefficient/runtime dependency only",
            "dR_e_dphi": "NO_NEWTON_BLOCK_PHI_IS_PRESCRIBED_FUNCTION",
            "dR_e_du_v_species": "NO_DIRECT_DEPENDENCY",
        },
        "r3_e0_state_specific_zero_paths": {
            "drift": "E=-grad(phi_prescribed)=0, so drift residual is zero",
            "uniform_diffusion": (
                "initial n_e is uniform, so grad(n_e)=0 and the diffusion flux is zero "
                "even though D_e structurally depends on p"
            ),
            "source": "no electron source kernel is inserted by the R3 recipe",
        },
        "explicit_electron_fvbc_objects_present": explicit_electron_fvbc,
        "electron_bc_interpretation": (
            "Issue91 inserts no explicit electron FVBC object; J1 preserves that contract "
            "and relies on framework-effective boundary behavior, to be validated by P2/P3"
        ),
        "reciprocal_heavy_dependencies": reciprocal,
        "j1_prediction": (
            "With p and T_g frozen and E=0, the retained electron equation is linear in n_e. "
            "For the uniform initial state, time/diffusion/drift residuals should form a null-flux "
            "invariant subject to framework-effective FV boundary/runtime semantics."
        ),
        "status": "J0_COMPLETE",
    }
    return report


def _top_level_block(text: str, name: str) -> str:
    """Return one modern-MOOSE top-level block, or an empty string if absent."""
    lines = text.splitlines()
    start = None
    depth = 0
    out: list[str] = []
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if start is None:
            if stripped == f"[{name}]":
                start = i
                depth = 1
                out.append(raw)
            continue
        out.append(raw)
        if stripped.startswith("[") and stripped.endswith("]"):
            if stripped == "[]":
                depth -= 1
                if depth == 0:
                    return "\n".join(out)
            elif not stripped.startswith("[!"):
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
