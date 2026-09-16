#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

REL_L2_TOL = 1.0e-7
REL_LINF_TOL = 1.0e-7
INVENTORY_REL_TOL = 1.0e-8

REQUIRED = {
    "time",
    "control_avg",
    "candidate_avg",
    "control_min",
    "candidate_min",
    "control_max",
    "control_inventory",
    "candidate_inventory",
    "error_l2_sq",
    "control_l2_sq",
    "error_linf",
}


def _metrics(rows: list[dict[str, float]]) -> dict[str, float | bool]:
    if len(rows) < 2:
        raise ValueError("need INITIAL plus at least one solved timestep row")

    initial = rows[0]
    solved = rows[1:]
    initial_inventory = initial["control_inventory"]
    if not math.isfinite(initial_inventory) or initial_inventory <= 0.0:
        raise ValueError("invalid initial control inventory")

    max_rel_l2 = 0.0
    max_rel_linf = 0.0
    max_control_inventory_drift = 0.0
    max_candidate_inventory_drift = 0.0
    min_candidate_density = math.inf

    for row in solved:
        if row["control_l2_sq"] <= 0.0 or row["control_max"] <= 0.0:
            raise ValueError("invalid control norm in solved row")
        rel_l2 = math.sqrt(max(row["error_l2_sq"], 0.0) / row["control_l2_sq"])
        rel_linf = row["error_linf"] / row["control_max"]
        control_drift = abs(row["control_inventory"] - initial_inventory) / initial_inventory
        candidate_drift = abs(row["candidate_inventory"] - initial_inventory) / initial_inventory
        max_rel_l2 = max(max_rel_l2, rel_l2)
        max_rel_linf = max(max_rel_linf, rel_linf)
        max_control_inventory_drift = max(max_control_inventory_drift, control_drift)
        max_candidate_inventory_drift = max(max_candidate_inventory_drift, candidate_drift)
        min_candidate_density = min(min_candidate_density, row["candidate_min"])

    initial_avg_rel = abs(initial["candidate_avg"] - initial["control_avg"]) / initial["control_avg"]
    initial_inventory_rel = abs(initial["candidate_inventory"] - initial_inventory) / initial_inventory

    checks = {
        "initial_representation_match": initial_avg_rel <= REL_L2_TOL and initial_inventory_rel <= REL_L2_TOL,
        "candidate_positive": min_candidate_density > 0.0,
        "representation_rel_l2": max_rel_l2 <= REL_L2_TOL,
        "representation_rel_linf": max_rel_linf <= REL_LINF_TOL,
        "control_inventory_conservative": max_control_inventory_drift <= INVENTORY_REL_TOL,
        "candidate_inventory_conservative": max_candidate_inventory_drift <= INVENTORY_REL_TOL,
    }

    return {
        "initial_avg_rel": initial_avg_rel,
        "initial_inventory_rel": initial_inventory_rel,
        "max_rel_l2": max_rel_l2,
        "max_rel_linf": max_rel_linf,
        "max_control_inventory_drift": max_control_inventory_drift,
        "max_candidate_inventory_drift": max_candidate_inventory_drift,
        "min_candidate_density": min_candidate_density,
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "failed_checks": sorted(k for k, ok in checks.items() if not ok),
    }


def _read_csv(path: Path) -> list[dict[str, float]]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing CSV columns: {sorted(missing)}")
        rows = []
        for raw in reader:
            row = {k: float(raw[k]) for k in REQUIRED}
            if not all(math.isfinite(v) for v in row.values()):
                raise ValueError("non-finite CSV value")
            rows.append(row)
    return rows


def _self_test() -> dict[str, object]:
    base = {
        "time": 0.0,
        "control_avg": 1.0,
        "candidate_avg": 1.0,
        "control_min": 0.8,
        "candidate_min": 0.8,
        "control_max": 1.2,
        "control_inventory": 1.0,
        "candidate_inventory": 1.0,
        "error_l2_sq": 0.0,
        "control_l2_sq": 1.0,
        "error_linf": 0.0,
    }
    good = [dict(base), dict(base, time=0.01, error_l2_sq=1e-18, error_linf=1e-9)]
    bad_rep = [dict(base), dict(base, time=0.01, error_l2_sq=1e-8, error_linf=1e-4)]
    bad_pos = [dict(base), dict(base, time=0.01, candidate_min=-1.0)]
    bad_inventory = [dict(base), dict(base, time=0.01, candidate_inventory=1.01)]

    checks = {
        "positive_control_passes": _metrics(good)["status"] == "PASS",
        "representation_mutation_rejected": _metrics(bad_rep)["status"] == "FAIL",
        "positivity_mutation_rejected": _metrics(bad_pos)["status"] == "FAIL",
        "inventory_mutation_rejected": _metrics(bad_inventory)["status"] == "FAIL",
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "failed_checks": sorted(k for k, ok in checks.items() if not ok),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        result = _self_test()
    else:
        if args.csv is None:
            ap.error("--csv is required unless --self-test is used")
        result = _metrics(_read_csv(args.csv))

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
