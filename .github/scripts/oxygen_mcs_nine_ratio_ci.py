#!/usr/bin/env python3
"""Compute nine MCS/MOOSE coefficient ratios in an authorized CI runner.

Use only with the Issue #432 guarded workflow; keep private lookup input inside
the runner. Ratios are reversible using MCS references: their release requires
explicit authorization separate from the approved PNG disclosure.
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

from oxygen_mcs_rate_compare_ci import PANEL_REACTIONS, prepare_linear_comparison

OUTPUT = "MCS_MOOSE_9_reaction_ratios.csv"
FIELDS = (
    "reaction", "case", "mean_energy_eV", "moose_over_mcs",
    "comparison_status", "scientific_status",
)


def ratio_rows(panels):
    if tuple(p["reaction"] for p in panels) != PANEL_REACTIONS:
        raise ValueError("Nine-channel panel identity mismatch")
    result = []
    for panel in panels:
        energies, mcs_rates, moose_rates = (
            panel["energies"], panel["mcs"], panel["moose"]
        )
        if not len(energies) == len(mcs_rates) == len(moose_rates) == 24:
            raise ValueError("Invalid twenty-four case coverage")
        if any(not math.isfinite(float(e)) or float(e) <= 0 for e in energies):
            raise ValueError("Invalid mean-energy grid")
        for index, (energy, mcs, moose) in enumerate(
            zip(energies, mcs_rates, moose_rates), 1
        ):
            if mcs is None:
                raise ValueError("All nine channels require verified MCS references")
            if not math.isfinite(mcs) or mcs < 0:
                raise ValueError("Invalid MCS input")
            if moose is not None and (not math.isfinite(moose) or moose < 0):
                raise ValueError("Invalid MOOSE input")
            if mcs == 0:
                status, ratio = "ZERO_MCS_NO_RATIO", ""
            elif moose is None:
                status, ratio = "OUTSIDE_LOOKUP_OR_FORMULA_DOMAIN", ""
            else:
                status, ratio = "MATCHED", format(moose / mcs, ".10g")
            result.append({
                "reaction": f'EI-{panel["reaction"]}',
                "case": index,
                "mean_energy_eV": format(float(energy), ".12g"),
                "moose_over_mcs": ratio,
                "comparison_status": status,
                "scientific_status": (
                    "REACTION_IDENTITY_HOLD" if panel["reaction"] in (411, 412)
                    else "MCS_UNIT_CONFIRMATION_HOLD"
                ),
            })
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rate-dir", required=True, type=Path)
    parser.add_argument("--mcs-csv", required=True, type=Path)
    parser.add_argument("--additional-mcs-csv", action="append", default=[], type=Path)
    parser.add_argument("--public-rate-dir", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        paths = [args.mcs_csv, *args.additional_mcs_csv]
        panels = prepare_linear_comparison(
            args.rate_dir, paths, public_rate_dir=args.public_rate_dir,
            require_complete=True,
        )
        rows = ratio_rows(panels)
        if args.output_dir.exists() and any(args.output_dir.iterdir()):
            raise ValueError("Output folder must be empty")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = args.output_dir / OUTPUT
        with output_path.open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    except Exception:
        parser.exit(2, "MCS_NINE_RATIO_FAILED: secure input validation failed\n")
    print("MCS_NINE_RATIO_CSV_GENERATED_IN_RUNNER", len(PANEL_REACTIONS), len(rows))


if __name__ == "__main__":
    main()
