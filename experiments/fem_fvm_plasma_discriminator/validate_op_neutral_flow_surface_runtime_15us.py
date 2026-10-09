#!/usr/bin/env python3
"""Runtime gate for Issue #331 Stage-B v4 surface-coupled 15 us discriminator."""
from __future__ import annotations

import csv
import math

import validate_op_neutral_flow_runtime_15us as base_gate

RATE_COLUMNS = (
    "stageb4_O_surface_loss_rate",
    "stageb4_O2s_surface_loss_rate",
    "stageb4_Os_surface_loss_rate",
    "stageb4_O2p_wall_mass_rate",
    "stageb4_Om_wall_mass_rate",
    "stageb4_Op_wall_mass_rate",
    "stageb4_ion_total_neutral_return_rate",
    "stageb4_ion_O_return_rate",
)


def relerr(a: float, b: float, floor: float = 1.0e-30) -> float:
    return abs(a - b) / max(abs(a), abs(b), floor)


def main() -> None:
    base_gate.main()

    with base_gate.CSV_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    for key in RATE_COLUMNS:
        if key not in rows[0]:
            raise SystemExit(f"missing Stage-B v4 reaction-rate column: {key}")

    max_total_return_rel = 0.0
    max_O_return_rel = 0.0
    min_rate = math.inf
    max_rate = 0.0

    for i, row in enumerate(rows):
        values: dict[str, float] = {}
        for key in RATE_COLUMNS:
            try:
                value = float(row[key])
            except (TypeError, ValueError) as exc:
                raise SystemExit(f"invalid {key} at row {i}: {row.get(key)!r}") from exc
            if not math.isfinite(value):
                raise SystemExit(f"non-finite {key} at row {i}: {value}")
            if value < -1.0e-24:
                raise SystemExit(f"unexpected negative reaction magnitude {key} at row {i}: {value}")
            values[key] = value
            min_rate = min(min_rate, value)
            max_rate = max(max_rate, value)

        ion_sum = (
            values["stageb4_O2p_wall_mass_rate"]
            + values["stageb4_Om_wall_mass_rate"]
            + values["stageb4_Op_wall_mass_rate"]
        )
        total_return = values["stageb4_ion_total_neutral_return_rate"]
        total_rel = relerr(ion_sum, total_return)
        max_total_return_rel = max(max_total_return_rel, total_rel)
        if total_rel > 5.0e-12:
            raise SystemExit(
                f"ion->neutral total-mass coupling failed at row {i}: "
                f"ions={ion_sum:.17g}, return={total_return:.17g}, rel={total_rel:.3e}"
            )

        O_ion_sum = (
            values["stageb4_Om_wall_mass_rate"]
            + values["stageb4_Op_wall_mass_rate"]
        )
        O_return = values["stageb4_ion_O_return_rate"]
        O_rel = relerr(O_ion_sum, O_return)
        max_O_return_rel = max(max_O_return_rel, O_rel)
        if O_rel > 5.0e-12:
            raise SystemExit(
                f"O-/O+ -> O coupling failed at row {i}: "
                f"ions={O_ion_sum:.17g}, return={O_return:.17g}, rel={O_rel:.3e}"
            )

    final = rows[-1]
    print("ISSUE331_STAGEB4_SURFACE_COUPLED_15US_GATE: PASS")
    print(f"rows={len(rows)}")
    print(f"final_time_us={float(final['time']) * 1e6:.17g}")
    print(f"reaction_rate_min_kg_s={min_rate:.17g}")
    print(f"reaction_rate_max_kg_s={max_rate:.17g}")
    print(f"ion_total_return_rel_error_max={max_total_return_rel:.17g}")
    print(f"ion_O_return_rel_error_max={max_O_return_rel:.17g}")
    for key in RATE_COLUMNS:
        print(f"final_{key}_kg_s={float(final[key]):.17g}")


if __name__ == "__main__":
    main()
