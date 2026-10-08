#!/usr/bin/env python3
"""Independent RF absorbed-power reference for Issue #202."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

import reference_chamber_fem as ref


def integrate_absorbed_power(coords, triangles, sol, sigma_real: float) -> tuple[float, float]:
    # Degree-3 exact 4-point triangle rule.  The integrand r*|E|^2 is cubic
    # for linear E and linear r, so this is exact on each linear triangle.
    qps = [
        (np.array([1.0 / 3.0] * 3), -27.0 / 48.0),
        (np.array([0.6, 0.2, 0.2]), 25.0 / 48.0),
        (np.array([0.2, 0.6, 0.2]), 25.0 / 48.0),
        (np.array([0.2, 0.2, 0.6]), 25.0 / 48.0),
    ]
    e2_volume = 0.0
    for ids, block in triangles:
        if block != "plasma":
            continue
        loc = np.asarray(ids, dtype=int)
        xy = coords[loc]
        area, _ = ref._element_geometry(xy)
        for lam, weight in qps:
            r = float(lam @ xy[:, 0])
            e = complex(lam @ sol[loc])
            e2_volume += 2.0 * math.pi * area * weight * r * (abs(e) ** 2)
    return 0.5 * sigma_real * e2_volume, e2_volume


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mesh", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--sigma-real", type=float, required=True)
    p.add_argument("--sigma-imag", type=float, required=True)
    p.add_argument("--source-scale", type=float, required=True)
    args = p.parse_args()

    ref.MATERIALS["plasma"] = (1.0, args.sigma_real, args.sigma_imag)
    ref.SOURCE = -1j * ref.OMEGA_MU0 * ref.J_COIL * args.source_scale

    coords, triangles = ref.load_mesh(args.mesh)
    mat, rhs = ref.assemble(coords, triangles)
    sol, _boundary, rel_res = ref.solve(coords, mat, rhs)
    if not math.isfinite(rel_res) or rel_res > 1e-10:
        raise RuntimeError(f"reference solve residual too large: {rel_res:.3e}")

    p_abs, e2_volume = integrate_absorbed_power(coords, triangles, sol, args.sigma_real)
    report = {
        "issue": 202,
        "status": "REFERENCE_GENERATED",
        "sigma_real_S_per_m": args.sigma_real,
        "sigma_imag_S_per_m": args.sigma_imag,
        "source_scale": args.source_scale,
        "P_abs_W": p_abs,
        "integral_abs_E_squared_dV": e2_volume,
        "max_abs_E_V_per_m": float(np.max(np.abs(sol))),
        "relative_linear_residual": rel_res,
        "formula": "0.5*sigma_R*integral(|E|^2 dV)",
        "phasor": "exp(+i omega t), peak",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
