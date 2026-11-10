#!/usr/bin/env python3
"""Numerical no-op parity oracle for Issue402 external-only PhysicsBase pilot.

This is intentionally a microscopic diffusion fixture, NOT an S6 plasma
simulation. A separate full 400 W 100us S5/S6 migrated-input parity gate is
required once actual equation-building DSL is implemented.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", required=True, type=Path)
    p.add_argument("--candidate", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    report = {
        "schema": "issue402.g1.native.external_binding_parity.v1",
        "scope": "tiny FEM+FV diffusion fixture only; no plasma Chemistry or S6 equivalence",
        "result": "NOT_EVALUATED",
        "direct_jacobian_matrix_comparison": "NOT_EVALUATED",
    }
    try:
        with netcdf_file(args.baseline, "r", mmap=False) as ref, netcdf_file(
            args.candidate, "r", mmap=False
        ) as trial:
            watched = sorted(
                name for name in ref.variables
                if name in {"time_whole", "coordx", "coordy", "coordz"}
                or name.startswith(("vals_nod_var", "vals_elem_var", "vals_glo_var"))
            )
            if not watched:
                raise ValueError("No physical Exodus state variables found")
            for name in watched:
                if name not in trial.variables:
                    raise ValueError(f"Exodus field missing: {name}")
                a = np.asarray(ref.variables[name].data)
                b = np.asarray(trial.variables[name].data)
                if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
                    raise ValueError(f"Shape or finite state mismatch: {name}")
                if not np.allclose(a, b, rtol=1e-12, atol=1e-12):
                    raise ValueError(f"Numerical discrepancy from external-only action: {name}")
            report["compared_exodus_fields"] = watched
            report["result"] = "TINY_DIFFUSION_NATIVE_NUMERICAL_PARITY_PASS"
        print(report["result"])
    except Exception as exc:
        report["result"] = "NATIVE_PARITY_NOT_PROVEN"
        report["reason"] = str(exc)
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
