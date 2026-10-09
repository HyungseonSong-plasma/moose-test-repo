#!/usr/bin/env python3
"""Runtime gate for Issue #331 Stage-B neutral-flow + charged-DD 15 us discriminator."""
from __future__ import annotations

import csv
import math
from pathlib import Path

import prepare_op_neutral_flow_staged_15us as case

CSV_PATH = Path(case.CASE_NAME + "_out.csv")
TIME_SEQUENCE = case.staged.time_sequence()
EXPECTED_ROWS = len(TIME_SEQUENCE)
NEUTRALITY_SCALE = 2.0e15
NEUTRALITY_REL_TOL = 1.0e-9
SIMPLEX_TOL = 2.0e-10
MASS_CLOSURE_REL_TOL = 2.0e-9
OUTLET_CLOSURE_REL_TOL = 2.0e-7

REQUIRED = (
    "time",
    "charge_integral",
    "charge_number_min",
    "charge_number_max",
    "mean_energy_min",
    "mean_energy_max",
    "ne_min",
    "ne_max",
    "ni_min",
    "ni_max",
    "nm_min",
    "nm_max",
    "nop_min",
    "nop_max",
    "potential_min",
    "potential_max",
    "neutral_sum_w_min",
    "neutral_sum_w_max",
    "w_O2_min",
    "w_O2_max",
    "w_O2s_min",
    "w_O2s_max",
    "w_O_min",
    "w_O_max",
    "w_Os_min",
    "w_Os_max",
    "neutral_Mn_min",
    "neutral_Mn_max",
    "neutral_rho_min",
    "neutral_rho_max",
    "neutral_p_min",
    "neutral_p_max",
    "neutral_u_min",
    "neutral_u_max",
    "neutral_v_min",
    "neutral_v_max",
    "neutral_mass_total",
    "neutral_mass_O2",
    "neutral_mass_O2s",
    "neutral_mass_O",
    "neutral_mass_Os",
    "neutral_outlet_mass",
    "neutral_outlet_mdot_O2",
    "neutral_outlet_mdot_O2s",
    "neutral_outlet_mdot_O",
    "neutral_outlet_mdot_Os",
)


def finite(row: dict[str, str], key: str, index: int) -> float:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"invalid {key} at row {index}: {row.get(key)!r}") from exc
    if not math.isfinite(value):
        raise SystemExit(f"non-finite {key} at row {index}: {value}")
    return value


def relerr(a: float, b: float, floor: float = 1.0e-30) -> float:
    return abs(a - b) / max(abs(a), abs(b), floor)


def main() -> None:
    case.validate_analytic_constraints()

    if not CSV_PATH.exists():
        raise SystemExit(f"missing runtime CSV: {CSV_PATH}")
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    if len(rows) != EXPECTED_ROWS:
        raise SystemExit(f"row-count gate failed: expected {EXPECTED_ROWS}, got {len(rows)}")
    for key in REQUIRED:
        if key not in rows[0]:
            raise SystemExit(f"missing postprocessor column: {key}")

    max_simplex_error = 0.0
    max_mass_closure = 0.0
    max_outlet_closure = 0.0
    max_abs_charge_number = 0.0
    max_abs_charge_integral = 0.0

    for i, row in enumerate(rows):
        values = {key: finite(row, key, i) for key in REQUIRED}
        expected_t = TIME_SEQUENCE[i]
        if not math.isclose(values["time"], expected_t, rel_tol=2.0e-12, abs_tol=2.0e-15):
            raise SystemExit(
                f"time-grid gate failed at row {i}: t={values['time']:.17g}, "
                f"expected={expected_t:.17g}"
            )
        if i and values["time"] <= float(rows[i - 1]["time"]):
            raise SystemExit(f"non-increasing time at row {i}")

        # Charged / electron baseline remains positive and ordered.
        for prefix in ("ne", "ni", "nm", "nop"):
            lo = values[f"{prefix}_min"]
            hi = values[f"{prefix}_max"]
            if lo <= 0.0 or hi <= 0.0 or lo > hi:
                raise SystemExit(
                    f"{prefix} positivity/order gate failed at row {i}: [{lo}, {hi}]"
                )
        if values["mean_energy_min"] <= 0.0 or values["mean_energy_min"] > values["mean_energy_max"]:
            raise SystemExit(
                f"mean-energy positivity/order gate failed at row {i}: "
                f"[{values['mean_energy_min']}, {values['mean_energy_max']}]"
            )
        if values["potential_min"] > values["potential_max"]:
            raise SystemExit(f"potential ordering gate failed at row {i}")
        if values["charge_number_min"] > values["charge_number_max"]:
            raise SystemExit(f"charge ordering gate failed at row {i}")

        max_abs_charge_number = max(
            max_abs_charge_number,
            abs(values["charge_number_min"]),
            abs(values["charge_number_max"]),
        )
        max_abs_charge_integral = max(max_abs_charge_integral, abs(values["charge_integral"]))

        # Neutral Q-1 simplex: constrained O2 plus three solved neutrals.
        for species in ("w_O2", "w_O2s", "w_O", "w_Os"):
            lo = values[f"{species}_min"]
            hi = values[f"{species}_max"]
            if lo < -SIMPLEX_TOL or hi > 1.0 + SIMPLEX_TOL or lo > hi:
                raise SystemExit(
                    f"neutral mass-fraction gate failed at row {i} for {species}: [{lo}, {hi}]"
                )

        simplex_error = max(
            abs(values["neutral_sum_w_min"] - 1.0),
            abs(values["neutral_sum_w_max"] - 1.0),
        )
        max_simplex_error = max(max_simplex_error, simplex_error)
        if simplex_error > SIMPLEX_TOL:
            raise SystemExit(
                f"neutral simplex closure failed at row {i}: "
                f"sum_w=[{values['neutral_sum_w_min']:.17g},"
                f"{values['neutral_sum_w_max']:.17g}]"
            )

        if values["neutral_Mn_min"] < 0.016 - 1.0e-12 or values["neutral_Mn_max"] > 0.032 + 1.0e-12:
            raise SystemExit(
                f"neutral mean molar mass out of oxygen bounds at row {i}: "
                f"[{values['neutral_Mn_min']}, {values['neutral_Mn_max']}]"
            )
        if values["neutral_rho_min"] <= 0.0 or values["neutral_p_min"] <= 0.0:
            raise SystemExit(
                f"neutral density/pressure non-positive at row {i}: "
                f"rho_min={values['neutral_rho_min']}, p_min={values['neutral_p_min']}"
            )

        species_mass = (
            values["neutral_mass_O2"]
            + values["neutral_mass_O2s"]
            + values["neutral_mass_O"]
            + values["neutral_mass_Os"]
        )
        mass_err = relerr(species_mass, values["neutral_mass_total"])
        max_mass_closure = max(max_mass_closure, mass_err)
        if mass_err > MASS_CLOSURE_REL_TOL:
            raise SystemExit(
                f"neutral inventory closure failed at row {i}: species={species_mass:.17g}, "
                f"total={values['neutral_mass_total']:.17g}, rel={mass_err:.3e}"
            )

        outlet_species = (
            values["neutral_outlet_mdot_O2"]
            + values["neutral_outlet_mdot_O2s"]
            + values["neutral_outlet_mdot_O"]
            + values["neutral_outlet_mdot_Os"]
        )
        outlet_total = values["neutral_outlet_mass"]
        if max(abs(outlet_species), abs(outlet_total)) > 1.0e-20:
            outlet_err = relerr(outlet_species, outlet_total, 1.0e-20)
            max_outlet_closure = max(max_outlet_closure, outlet_err)
            if outlet_err > OUTLET_CLOSURE_REL_TOL:
                raise SystemExit(
                    f"neutral outlet species/total closure failed at row {i}: "
                    f"species={outlet_species:.17g}, total={outlet_total:.17g}, rel={outlet_err:.3e}"
                )

    initial_charge = max(
        abs(float(rows[0]["charge_number_min"])),
        abs(float(rows[0]["charge_number_max"])),
    )
    if initial_charge > NEUTRALITY_REL_TOL * NEUTRALITY_SCALE:
        raise SystemExit(
            f"initial charge neutrality gate failed: |nq|max={initial_charge:.17g} m^-3"
        )

    if not math.isclose(float(rows[-1]["time"]), 15.0e-6, rel_tol=2.0e-12, abs_tol=2.0e-15):
        raise SystemExit(f"final time is not 15 us: {rows[-1]['time']}")

    inlet_sum = (
        case.INLET_MDOT_O2
        + case.INLET_MDOT_O2S
        + case.INLET_MDOT_O
        + case.INLET_MDOT_OS
    )
    if relerr(inlet_sum, case.INLET_MDOT) > 1.0e-14:
        raise SystemExit("analytic inlet species mass-flow closure changed")

    print("ISSUE331_STAGEB_NEUTRAL_FLOW_15US_GATE: PASS")
    print(f"rows={len(rows)}")
    print(f"final_time_us={float(rows[-1]['time']) * 1e6:.17g}")
    print(f"initial_charge_abs_max_m-3={initial_charge:.17g}")
    print(f"trajectory_charge_abs_max_m-3={max_abs_charge_number:.17g}")
    print(f"trajectory_abs_charge_integral_C_max={max_abs_charge_integral:.17g}")
    print(f"neutral_simplex_error_max={max_simplex_error:.17g}")
    print(f"neutral_inventory_rel_error_max={max_mass_closure:.17g}")
    print(f"neutral_outlet_rel_error_max={max_outlet_closure:.17g}")
    print(f"analytic_inlet_mdot_kg_s={case.INLET_MDOT:.17g}")
    print(f"analytic_inlet_species_mdot_sum_kg_s={inlet_sum:.17g}")
    print(f"analytic_neutral_Mn_kg_mol={case.M_INLET:.17g}")

    snapshots = {
        0: "0",
        100: "100ns",
        120: "300ns",
        190: "1us",
        280: "10us",
        281: "11us",
        282: "12us",
        283: "13us",
        284: "14us",
        285: "15us",
    }
    for idx, label in snapshots.items():
        row = rows[idx]
        print(
            f"snapshot={label} t_s={float(row['time']):.17g} "
            f"p=[{float(row['neutral_p_min']):.17g},{float(row['neutral_p_max']):.17g}] "
            f"rho=[{float(row['neutral_rho_min']):.17g},{float(row['neutral_rho_max']):.17g}] "
            f"u=[{float(row['neutral_u_min']):.17g},{float(row['neutral_u_max']):.17g}] "
            f"v=[{float(row['neutral_v_min']):.17g},{float(row['neutral_v_max']):.17g}] "
            f"sumw=[{float(row['neutral_sum_w_min']):.17g},{float(row['neutral_sum_w_max']):.17g}] "
            f"wO2=[{float(row['w_O2_min']):.17g},{float(row['w_O2_max']):.17g}] "
            f"wO=[{float(row['w_O_min']):.17g},{float(row['w_O_max']):.17g}] "
            f"ne=[{float(row['ne_min']):.17g},{float(row['ne_max']):.17g}] "
            f"meanE=[{float(row['mean_energy_min']):.17g},{float(row['mean_energy_max']):.17g}]"
        )

    final = rows[-1]
    print(
        "final_charged="
        f"ne[{float(final['ne_min']):.17g},{float(final['ne_max']):.17g}] "
        f"O2+[{float(final['ni_min']):.17g},{float(final['ni_max']):.17g}] "
        f"O-[{float(final['nm_min']):.17g},{float(final['nm_max']):.17g}] "
        f"O+[{float(final['nop_min']):.17g},{float(final['nop_max']):.17g}]"
    )
    print(
        "final_phi_meanE="
        f"phi[{float(final['potential_min']):.17g},{float(final['potential_max']):.17g}] "
        f"meanE[{float(final['mean_energy_min']):.17g},{float(final['mean_energy_max']):.17g}]"
    )
    print("spatial_profile_evidence=Exodus contains charged + neutral flow/species state at INITIAL and every TIMESTEP_END")


if __name__ == "__main__":
    main()
