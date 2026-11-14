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


def nodal_names(exodus) -> list[str] | None:
    """Read Exodus node-variable identities; compare physical fields by name.

    Adding a separately constrained P2-only energy probe may change the
    on-disk variable index. Raw vals_nod_var# positional comparison would
    falsely classify two unchanged fields as a numerical discrepancy.
    """
    if "name_nod_var" not in exodus.variables:
        return None
    rows = np.asarray(exodus.variables["name_nod_var"].data)
    decoded = [np.asarray(row).tobytes().decode("ascii").split("\x00", 1)[0].strip()
               for row in rows]
    if not all(decoded) or len(decoded) != len(set(decoded)):
        raise ValueError("Nonunique/missing Exodus nodal variable names")
    return decoded


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
            ref_nodal = nodal_names(ref)
            trial_nodal = nodal_names(trial)
            if (ref_nodal is None) != (trial_nodal is None):
                raise ValueError("Exodus nodal identity metadata differs")
            node_source_to_trial = {}
            if ref_nodal is not None:
                for index, physical_name in enumerate(ref_nodal, start=1):
                    if physical_name not in trial_nodal:
                        raise ValueError(f"Physical nodal field missing: {physical_name}")
                    node_source_to_trial[f"vals_nod_var{index}"] = (
                        f"vals_nod_var{trial_nodal.index(physical_name)+1}")

            compared = []
            for name in watched:
                target = node_source_to_trial.get(name, name)
                if target not in trial.variables:
                    raise ValueError(f"Exodus field missing: {name} -> {target}")
                a = np.asarray(ref.variables[name].data)
                b = np.asarray(trial.variables[target].data)
                if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
                    raise ValueError(f"Shape or finite state mismatch: {name} -> {target}")
                if not np.allclose(a, b, rtol=1e-12, atol=1e-12):
                    raise ValueError(f"Numerical discrepancy from external-only action: {name} -> {target}")
                compared.append({"baseline": name, "candidate": target})
            report["compared_exodus_fields"] = compared
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
