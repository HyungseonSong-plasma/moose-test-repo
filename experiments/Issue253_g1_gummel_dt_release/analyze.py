#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / "generated"
RESULTS = ROOT / "results"

REFERENCE_FAMILY_PHI_EINF = 0.10
MATERIAL_IMPROVEMENT_FACTOR = 0.75


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _final_profile(case_dir: Path) -> list[tuple[float, float, float]]:
    candidates: list[tuple[int, Path]] = []
    for path in case_dir.glob("input_out_electron_profile_*.csv"):
        match = re.search(r"_([0-9]+)\.csv$", path.name)
        if match:
            candidates.append((int(match.group(1)), path))
    if not candidates:
        raise RuntimeError(f"{case_dir.name}: no electron profile output")
    _, path = max(candidates)
    points: list[tuple[float, float, float]] = []
    for row in _rows(path):
        points.append(
            (
                float(row["x"]),
                float(row["electron_density_out"]),
                float(row["potential_from_poisson"]),
            )
        )
    points.sort()
    if len(points) < 3:
        raise RuntimeError(f"{case_dir.name}: insufficient profile points")
    return points


def _final_scalar(case_dir: Path) -> dict[str, float]:
    path = case_dir / "input_out.csv"
    if not path.exists():
        raise RuntimeError(f"{case_dir.name}: missing input_out.csv")
    rows = _rows(path)
    physical = [r for r in rows if float(r.get("time", "0")) > 0.0]
    if not physical:
        raise RuntimeError(f"{case_dir.name}: no physical CSV rows")
    row = physical[-1]
    out: dict[str, float] = {"time": float(row["time"])}
    for key in (
        "electron_inventory",
        "n_e_min",
        "n_e_max",
        "phi_min",
        "phi_max",
        "fixed_point_iterations",
    ):
        if key in row and row[key] != "":
            out[key] = float(row[key])
    return out


def _field(points: list[tuple[float, float, float]]) -> list[float]:
    x = [p[0] for p in points]
    phi = [p[2] for p in points]
    e: list[float] = []
    for i in range(len(points)):
        if i == 0:
            grad = (phi[1] - phi[0]) / (x[1] - x[0])
        elif i == len(points) - 1:
            grad = (phi[-1] - phi[-2]) / (x[-1] - x[-2])
        else:
            grad = (phi[i + 1] - phi[i - 1]) / (x[i + 1] - x[i - 1])
        e.append(-grad)
    return e


def _profile_metrics(
    ref: list[tuple[float, float, float]],
    case: list[tuple[float, float, float]],
) -> dict[str, float]:
    if len(ref) != len(case):
        raise RuntimeError("profile point counts differ")
    for a, b in zip(ref, case):
        if not math.isclose(a[0], b[0], rel_tol=0.0, abs_tol=1e-14):
            raise RuntimeError("profile coordinates differ")

    ref_phi = [p[2] - ref[-1][2] for p in ref]
    case_phi = [p[2] - case[-1][2] for p in case]
    phi_scale = max(max(abs(v) for v in ref_phi), 1e-30)
    phi_err = [abs(a - b) for a, b in zip(case_phi, ref_phi)]

    ref_ne = [p[1] for p in ref]
    case_ne = [p[1] for p in case]
    ne_scale = max(max(abs(v) for v in ref_ne), 1.0)
    ne_err = [abs(a - b) for a, b in zip(case_ne, ref_ne)]

    ref_e = _field(ref)
    case_e = _field(case)
    e_scale = max(max(abs(v) for v in ref_e), 1e-30)
    e_err = [abs(a - b) for a, b in zip(case_e, ref_e)]

    return {
        "phi_einf": max(phi_err) / phi_scale,
        "phi_relative_rms": math.sqrt(sum(v * v for v in phi_err) / len(phi_err)) / phi_scale,
        "ne_einf": max(ne_err) / ne_scale,
        "e_einf": max(e_err) / e_scale,
        "delta_phi_ratio": (
            (max(case_phi) - min(case_phi))
            / max(max(ref_phi) - min(ref_phi), 1e-30)
        ),
    }


def main() -> int:
    ref_dir = GENERATED / "ref_chi0p1"
    one_dir = GENERATED / "onepass_chi5"
    gum_dir = GENERATED / "gummel_chi5"

    ref = _final_profile(ref_dir)
    one = _final_profile(one_dir)
    gum = _final_profile(gum_dir)

    one_metrics = _profile_metrics(ref, one)
    gum_metrics = _profile_metrics(ref, gum)
    scalar = {
        "ref_chi0p1": _final_scalar(ref_dir),
        "onepass_chi5": _final_scalar(one_dir),
        "gummel_chi5": _final_scalar(gum_dir),
    }

    if one_metrics["phi_einf"] < 1.0:
        classification = "BASELINE_NOT_REPRODUCED"
        valid = False
    elif scalar["gummel_chi5"].get("fixed_point_iterations", 0.0) <= 1.0:
        classification = "GUMMEL_NOT_EXERCISED"
        valid = False
    elif (
        gum_metrics["phi_einf"] <= REFERENCE_FAMILY_PHI_EINF
        and gum_metrics["ne_einf"] <= REFERENCE_FAMILY_PHI_EINF
    ):
        classification = "DT_RELEASE_SUPPORTED"
        valid = True
    elif gum_metrics["phi_einf"] <= MATERIAL_IMPROVEMENT_FACTOR * one_metrics["phi_einf"]:
        classification = "PARTIAL_RELEASE"
        valid = True
    else:
        classification = "NO_MATERIAL_BENEFIT"
        valid = True

    summary = {
        "issue": 253,
        "comparison": "chi=5 Gummel vs chi=5 one-pass against chi=0.1 reference",
        "equal_physical_time": True,
        "thresholds": {
            "reference_family_phi_einf": REFERENCE_FAMILY_PHI_EINF,
            "material_improvement_factor": MATERIAL_IMPROVEMENT_FACTOR,
        },
        "onepass_chi5": one_metrics,
        "gummel_chi5": gum_metrics,
        "scalars": scalar,
        "classification": classification,
        "evidence_valid": valid,
        "gauss_is_hard_gate": False,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "analysis.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("ISSUE253_G1_CLASSIFICATION:", classification)
    print("ISSUE253_G1_ANALYSIS:", out)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
