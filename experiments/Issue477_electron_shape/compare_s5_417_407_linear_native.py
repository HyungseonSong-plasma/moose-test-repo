#!/usr/bin/env python3
"""Fail-closed native S5-417-407 replay comparison for PR #488.

Baseline: completed immutable Oxygen14 S5 artifact 13641179390.
Candidate: fresh 400 W / 100 us build of PR #488 C++ rate material
           substituted ONLY onto original pinned source tree.
No private rate bytes are copied into the published comparison artifact.
This compares nonlinear solver convergence history as a Jacobian-sensitive
proxy, but DOES NOT claim direct matrix/Jacobian equality.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file

CASE = "S5-417-407"
NA = 6.02214076e23
TIMES_US = (25, 50, 75, 100)
REL_LIMIT = 1e-3  # 0.1% normalized max error in meaningful physical fields
POINT_LIMIT = 5e-3  # 0.5% pointwise; disallow localized jumps
REQUIRED_CSV = (
    "ne_max", "ne_min", "mean_energy_max", "mean_energy_min",
    "P_rf_raw_W_t6", "P_rf_scaled_W_t6", "ei415_R_ion_O2_integral",
    "legacy8_407_rate_integral",
)


def reject(message: str) -> None:
    raise ValueError("NATIVE_PARITY_NOT_PROVEN: " + message)


def read_csv(path: Path) -> tuple[list[str], dict[str, np.ndarray]]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        names = reader.fieldnames
        if not names or any(k not in names for k in REQUIRED_CSV + ("time",)):
            reject(f"required CSV data missing from {path}")
        rows = list(reader)
    if len(rows) != 461 or len(set(float(r["time"]) for r in rows)) != 461:
        reject(f"expected 461 unique time points, received {len(rows)}: {path}")
    output = {}
    for name in ("time", *REQUIRED_CSV):
        output[name] = np.array([float(r[name]) for r in rows], dtype=float)
        if not np.isfinite(output[name]).all():
            reject(f"nonfinite {name} in {path}")
    if not math.isclose(output["time"][-1], 1e-4, rel_tol=0, abs_tol=1e-13):
        reject(f"final simulation time was not 100 microseconds: {path}")
    return names, output


def normalized_metrics(a: np.ndarray, b: np.ndarray, label: str,
                       *, max_rel: float = REL_LIMIT, point_rel: float | None = None):
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        reject(f"{label}: shape mismatch or nonfinite data")
    scale = max(float(np.max(np.abs(a))), 1e-100)
    diff = b - a
    nrms = float(np.sqrt(np.mean(np.square(diff))) / scale)
    nmax = float(np.max(np.abs(diff)) / scale)
    if nrms > max_rel or nmax > max_rel:
        reject(f"{label}: nrms={nrms:.6g}, max-normalized={nmax:.6g} > {max_rel}")
    result = {"nrms": nrms, "normalized_max": nmax, "reference_scale": scale, "samples": int(a.size)}
    if point_rel is not None:
        # Ignore the unphysical almost-zero tail where tiny absolute differences
        # would produce arbitrarily large pointwise ratios.
        relevant = np.abs(a) > 1e-4 * scale
        if int(relevant.sum()) < 10:
            reject(f"{label}: insufficient physically significant samples")
        rel = np.abs(diff[relevant]) / np.maximum(np.abs(a[relevant]), 1e-100)
        pmax = float(np.max(rel))
        if pmax > point_rel:
            reject(f"{label}: localized relative deviation {pmax:.6g} > {point_rel}")
        result["pointwise_max_significant"] = pmax
    return result


def name_values(dataset, name: str, time_idx: int):
    raw = dataset.variables["name_nod_var"].data
    names = [b"".join(row).decode("utf-8").strip() for row in raw]
    if name not in names:
        reject(f"missing Exodus nodal variable {name}")
    return np.array(dataset.variables[f"vals_nod_var{names.index(name) + 1}"][time_idx], dtype=float)


def compare_exodus(original: Path, candidate: Path):
    results = {}
    with netcdf_file(original, "r", mmap=False) as a, netcdf_file(candidate, "r", mmap=False) as b:
        for name in ("coordx", "coordy"):
            av, bv = np.asarray(a.variables[name].data), np.asarray(b.variables[name].data)
            if av.shape != bv.shape or not np.array_equal(av, bv):
                reject(f"mesh {name} differs")
        ta = np.asarray(a.variables["time_whole"].data)
        tb = np.asarray(b.variables["time_whole"].data)
        if len(ta) != 461 or not np.array_equal(ta, tb):
            reject("Exodus time grids differ or not 461 states")
        for t in TIMES_US:
            index = int(np.argmin(np.abs(ta - t * 1e-6)))
            if abs(float(ta[index]) - t * 1e-6) > 1e-12:
                reject(f"missing Exodus {t}us frame")
            nea, neb = name_values(a, "log_ne", index), name_values(b, "log_ne", index)
            ena, enb = name_values(a, "log_energy", index), name_values(b, "log_energy", index)
            # In plasma domain log-ne is log(mol/m^3), while non-plasma nodes
            # are often exactly zero from Exodus variable mapping.
            mask = (nea < -5) & np.isfinite(nea) & np.isfinite(ena)
            if int(mask.sum()) < 200 or np.any(~np.isfinite(neb[mask])) or np.any(~np.isfinite(enb[mask])):
                reject(f"{t}us: plasma domain mask mismatch")
            if not np.array_equal((neb < -5)[mask], np.ones(int(mask.sum()), dtype=bool)):
                reject(f"{t}us: candidate plasma domain differs")
            n0, n1 = NA * np.exp(nea[mask]), NA * np.exp(neb[mask])
            Te0 = (2.0 / 3.0) * np.exp(ena[mask] - nea[mask])
            Te1 = (2.0 / 3.0) * np.exp(enb[mask] - neb[mask])
            for label, x0, x1 in (("electron_density", n0, n1), ("electron_temperature_eV", Te0, Te1)):
                results[f"{label}_{t}us"] = normalized_metrics(
                    x0, x1, f"{label}@{t}us", max_rel=REL_LIMIT, point_rel=POINT_LIMIT
                )
    return results


def convergence(path: Path):
    text = path.read_text(errors="replace")
    clean = re.sub(r"\x1b\[[0-9;]*m", "", text)
    iterations = [int(x) for x in re.findall(
        r"(?m)^\s*Nonlinear solve converged due to [A-Z_]+ iterations (\d+)\s*$", clean)]
    steps = [(int(i), float(t)) for i, t in re.findall(
        r"(?m)^Time Step (\d+), time = ([0-9.eE+-]+)", clean)]
    if len(iterations) != 460 or len(steps) != 461:
        reject(f"missing Newton iterations (got {len(iterations)}) or steps (got {len(steps)})")
    if "Solve failed" in clean or "DIVERGED_" in clean:
        reject(f"nonlinear divergence reported in {path}")
    if "Finished Executing" not in clean:
        reject(f"missing native completion in {path}")
    return iterations, steps


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    base, candidate = args.baseline, args.candidate
    evidence = {
        "schema": "issue477_pr488_linear_native_parity_v1",
        "case": CASE, "power_W": 400, "time_us": 100,
        "baseline_artifact_id": 13641179390,
        "source_sha": "29d1acc6ef7969908b86719e4b95c73a1565136d",
        "science_acceptance": "HOLD", "result": "NOT_EVALUATED",
        "jacobian_direct_matrix_comparison": "NOT_EVALUATED",
        "jacobian_proxy": "Newton step counts & full residual convergence",
    }
    try:
        bh, a = read_csv(base / "run/plasma.csv")
        ch, b = read_csv(candidate / "run/plasma.csv")
        if bh != ch or not np.array_equal(a["time"], b["time"]):
            reject("CSV schema or time grids differ")
        evidence["csv"] = {key: normalized_metrics(a[key], b[key], key)
                           for key in REQUIRED_CSV}
        evidence["spatial"] = compare_exodus(
            base / "run/plasma.e", candidate / "run/plasma.e")
        bi, bt = convergence(base / "runtime.log")
        ci, ct = convergence(candidate / "runtime.log")
        if bt != ct:
            reject("nonlinear step count/time sequence differs")
        mismatches = sum(x != y for x, y in zip(bi, ci))
        if mismatches:
            reject(f"Newton convergence iteration counts differ in {mismatches}/460 steps")
        evidence["solver"] = {
            "steps": 460, "newton_iterations_base": int(sum(bi)),
            "newton_iterations_candidate": int(sum(ci)),
            "iteration_sequence_equal": True,
        }
        evidence["result"] = "NUMERICAL_PROFILE_AND_CONVERGENCE_PASS"
        print("PR488_S5_417_407_NATIVE_NUMERICAL_PARITY_PASS")
    except Exception as exc:
        evidence["result"] = "FAIL_OR_INCOMPLETE"
        evidence["reason"] = str(exc)
        print("PR488_S5_417_407_NATIVE_PARITY_NOT_PROVEN", str(exc), flush=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2) + "\n")
        raise
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"result": evidence["result"], "solver": evidence["solver"],
                      "metrics": evidence["csv"]}, indent=2))


if __name__ == "__main__":
    main()
