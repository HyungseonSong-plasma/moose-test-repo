#!/usr/bin/env python3
"""Issue #245 T2 P3 evaluator with cancellation-safe molar-to-SI scaling gate.

The first T2 runtime established physical equivalence but the original G07
compared two accumulation rates formed by subtracting nearly equal inventory
snapshots after CSV serialization.  At dt=1e-10 s that subtraction amplified
ordinary output rounding to O(1e-10) relative error even though each inventory
snapshot independently obeyed the exact N_A*e conversion at O(1e-14).

This evaluator keeps the accumulation comparison as a diagnostic and qualifies
the exact unit conversion on directly corresponding observables: initial/final
energy inventories plus primary/SEE wall energy rates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from experiments.Issue245_t2_molar_electron_energy import p3_runtime as v1


def _direct_scaling_metrics(case_dir: Path, metrics: dict[str, Any]) -> dict[str, float]:
    rows = v1.w45.s5r._read_rows(case_dir / "input_out.csv")
    if len(rows) < 2:
        raise RuntimeError("P3 requires INITIAL and TIMESTEP_END rows")
    initial, final = rows[0], rows[-1]

    defects: dict[str, float] = {}
    for label, row in (("inventory_initial", initial), ("inventory_final", final)):
        molar_inventory = v1.w45.s5r._num(row, "s5r_n_epsilon_inventory")
        joule_inventory = v1.w45.s5r._num(row, v1.t2.ENERGY_INVENTORY_J)
        defects[label] = v1.w45._rel_defect(
            joule_inventory,
            molar_inventory * v1.ENERGY_MOLAR_TO_J,
        )

    previous = metrics["molar_to_si_scaling"]["relative_defects"]
    defects["primary_wall"] = previous["primary_wall"]
    defects["see_wall"] = previous["see_wall"]
    return defects


def _metrics(case_dir: Path, input_text: str) -> dict[str, Any]:
    metrics = v1._metrics(case_dir, input_text)
    original = dict(metrics["molar_to_si_scaling"]["relative_defects"])
    metrics["molar_to_si_scaling"]["diagnostic_accumulation_difference_defect"] = original[
        "accumulation"
    ]
    metrics["molar_to_si_scaling"]["relative_defects"] = _direct_scaling_metrics(
        case_dir, metrics
    )
    metrics["molar_to_si_scaling"]["gate_basis"] = (
        "direct initial/final inventory and wall-rate conversions; accumulation "
        "difference retained as non-gating CSV-cancellation diagnostic"
    )
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, default=Path("issue245-case"))
    parser.add_argument("--input-file", type=Path, default=Path("issue245-case/input.i"))
    parser.add_argument("--summary", type=Path, default=Path("issue245-logs/p3-summary.json"))
    args = parser.parse_args()

    input_text = args.input_file.read_text(encoding="utf-8")
    metrics = _metrics(args.case_dir, input_text)
    decision = v1._evaluate(metrics, input_text)
    summary = {
        "schema": "ISSUE245_T2_P3_V2",
        "claim": "coupled_one_step_log_molar_particle_plus_conservative_molar_energy",
        "evaluator_correction": (
            "G07 now gates direct molar-to-SI observables rather than a difference "
            "of nearly equal CSV-serialized inventories"
        ),
        "metrics": metrics,
        "decision": decision,
        "status": "PASS" if decision["scientific_hard_pass"] else "FAIL",
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.summary.read_text(encoding="utf-8"))
    return 0 if decision["scientific_hard_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
