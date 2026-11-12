#!/usr/bin/env python3
"""Native Exodus output completeness, NOT current/charge/sheath or science validation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file


def expected_times() -> np.ndarray:
    ns = (list(range(0, 101)) + list(range(110, 2001, 10))
          + list(range(2100, 10001, 100))
          + list(range(11000, 100001, 1000)))
    assert len(ns) == 461 and ns[-1] == 100000
    return np.asarray(ns, dtype=float) * 1e-9


def check_times(values: np.ndarray) -> None:
    expected = expected_times()
    if (values.shape != (461,) or not np.all(np.isfinite(values))
            or np.any(np.diff(values) <= 0)
            or np.max(np.abs(values - expected)) > 1e-14):
        raise ValueError("NATIVE_EXODUS_TIMEGRID_MISMATCH")


def decoded(rows) -> list[str]:
    return [bytes(row).decode("utf-8", "replace").strip("\x00 ").strip()
            for row in rows]


def check_exodus(path: Path) -> dict:
    if not path.is_file() or not path.stat().st_size:
        raise ValueError("NATIVE_EXODUS_MISSING")
    with netcdf_file(str(path), "r", mmap=False) as f:
        times = np.asarray(f.variables["time_whole"][:], dtype=float).copy()
        check_times(times)
        blocks = decoded(f.variables["eb_names"][:])
        if blocks.count("wafer_surface") != 1:
            raise ValueError("NATIVE_WAFER_SURFACE_BLOCK_MISSING_OR_DUPLICATE")
        block = blocks.index("wafer_surface") + 1
        connectivity = np.asarray(f.variables[f"connect{block}"][:])
        if connectivity.shape[0] != 27:
            raise ValueError("NATIVE_WAFER_FACE_COUNT_MISMATCH")
        fields = decoded(f.variables["name_elem_var"][:])
        if fields.count("sigma_wafer") != 1:
            raise ValueError("NATIVE_WAFER_SIGMA_MISSING_OR_DUPLICATE")
        name = f"vals_elem_var{fields.index('sigma_wafer') + 1}eb{block}"
        sigma = np.asarray(f.variables[name][:], dtype=float).copy()
    if sigma.shape != (461, 27) or not np.all(np.isfinite(sigma)):
        raise ValueError("NATIVE_WAFER_SIGMA_NONFINITE_OR_WRONG_SHAPE")
    return {
        "status": "ISSUE397_NATIVE_OUTPUT_COMPLETENESS_PASS",
        "time_points": 461,
        "final_time_us": float(times[-1] * 1e6),
        "wafer_faces": 27,
        "sigma_min_C_m2": float(sigma.min()),
        "sigma_max_C_m2": float(sigma.max()),
        "D1_current_charge_sheath_validation": "NOT_RUN_RETIRED",
        "science_acceptance": "NOT_ASSESSED",
    }


def self_test() -> None:
    original = expected_times()
    check_times(original)
    for bad in (original[:-1], np.concatenate([original[:100], original[99:]]),
                original * 0.999):
        try:
            check_times(bad)
        except ValueError:
            continue
        raise AssertionError("Incorrect time grid accepted")
    print("ISSUE397_OUTPUT_COMPLETENESS_SELFTEST_PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.input or not args.output:
        parser.error("--input and --output required")
    result = check_exodus(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(result["status"])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
