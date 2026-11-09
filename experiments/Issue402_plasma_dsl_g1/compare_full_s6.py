#!/usr/bin/env python3
"""Compare entire archived and migrated S6 Exodus outputs after both native runs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file


def compare(reference: Path, candidate: Path, *, rtol: float, atol: float) -> dict:
    with netcdf_file(reference, "r", mmap=False) as old, netcdf_file(
        candidate, "r", mmap=False
    ) as new:
        if set(old.dimensions) != set(new.dimensions):
            raise ValueError("Exodus dimensions differ")
        for dim in old.dimensions:
            if old.dimensions[dim] != new.dimensions[dim]:
                raise ValueError(f"Exodus dimension changed: {dim}")
        names = sorted(old.variables)
        if set(names) != set(new.variables):
            missing = sorted(set(names) - set(new.variables))
            extra = sorted(set(new.variables) - set(names))
            raise ValueError(f"Exodus variable names changed: missing={missing} extra={extra}")
        compared_fields = 0
        maximum_absolute_difference = 0.0
        for name in names:
            left = np.asarray(old.variables[name].data)
            right = np.asarray(new.variables[name].data)
            if left.shape != right.shape:
                raise ValueError(f"Exodus variable shape changed: {name}")
            if left.dtype.kind in "f":
                if not np.isfinite(left).all() or not np.isfinite(right).all():
                    raise ValueError(f"Nonfinite Exodus field: {name}")
                if left.size:
                    maximum_absolute_difference = max(
                        maximum_absolute_difference,
                        float(np.max(np.abs(left.astype(np.float64) -
                                            right.astype(np.float64)))),
                    )
                if not np.allclose(left, right, rtol=rtol, atol=atol):
                    raise ValueError(f"Numerical field mismatch: {name}")
                compared_fields += 1
            elif not np.array_equal(left, right):
                raise ValueError(f"Exact integer/metadata field mismatch: {name}")
        if not compared_fields:
            raise ValueError("No floating-point simulation fields found")
    return {
        "status": "S6_COMPLETE_EXODUS_FIELD_COMPARISON_PASS__SCIENTIFIC_HOLD",
        "reference": str(reference),
        "candidate": str(candidate),
        "relative_tolerance": rtol,
        "absolute_tolerance": atol,
        "compared_floating_fields": compared_fields,
        "max_absolute_difference": maximum_absolute_difference,
        "science_acceptance": "HOLD",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rtol", type=float, default=1e-11)
    parser.add_argument("--atol", type=float, default=1e-12)
    args = parser.parse_args()
    report = {"status": "NOT_EVALUATED", "science_acceptance": "HOLD"}
    try:
        if args.rtol < 0 or args.atol < 0:
            raise ValueError("Tolerances must be nonnegative")
        report = compare(args.reference, args.candidate, rtol=args.rtol, atol=args.atol)
    except Exception as exc:
        report = {
            "status": "S6_EXODUS_PARITY_NOT_PROVEN",
            "reason": str(exc),
            "science_acceptance": "HOLD",
        }
        raise
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])


if __name__ == "__main__":
    main()
