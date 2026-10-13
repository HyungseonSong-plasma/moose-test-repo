#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

E_CHARGE = 1.602176634e-19
ABS_Q = 2.0e-16
REL_Q = 2.0e-5

BASELINE_15US = {
    "charge_integral": 3.2363040870942e-08,
    "ne_min": 2.0923129982749e13,
    "ne_max": 9.9234573922351e14,
    "ni_min": 7.0629724794189e12,
    "ni_max": 9.9819212467240e14,
    "nm_min": 3.9037921724385e08,
    "nm_max": 1.5591007823092e15,
    "nop_min": 6.9080080445961e12,
    "nop_max": 9.9819212467240e14,
    "mean_energy_min": 1.9721827182918e-02,
    "mean_energy_max": 7.6100081688538e-02,
    "potential_min": 0.0,
    "potential_max": 4.1284905756655,
    "neutral_p_min": 1.3088377762991,
    "neutral_p_max": 1.3388587303504,
    "neutral_mass_total": 6.9864337904466e-07,
    "neutral_Mn_min": 2.6084015381654e-02,
    "neutral_Mn_max": 2.6688762772231e-02,
    "neutral_rho_min": 1.3928030414420e-05,
    "neutral_rho_max": 1.4107163695107e-05,
    "neutral_u_min": -2.3053420747205,
    "neutral_u_max": 2.8825754457585,
    "neutral_v_min": -2.7387341393238,
    "neutral_v_max": 2.8263996656993,
    "w_O2_min": 0.72164836593559,
    "w_O2_max": 0.76895766871922,
    "w_O2s_min": 0.032035832811877,
    "w_O2s_max": 0.05154665286096,
    "w_O_min": 0.090431963261396,
    "w_O_max": 0.10309321925384,
    "w_Os_min": 0.10857453520751,
    "w_Os_max": 0.12371176194961,
}

REQUIRED = [
    "time", "charge_integral",
    "ne_min", "ne_max", "ni_min", "ni_max", "nm_min", "nm_max", "nop_min", "nop_max",
    "mean_energy_min", "mean_energy_max", "potential_min", "potential_max",
    "neutral_p_min", "neutral_p_max", "neutral_mass_total",
    "neutral_Mn_min", "neutral_Mn_max", "neutral_rho_min", "neutral_rho_max",
    "neutral_u_min", "neutral_u_max", "neutral_v_min", "neutral_v_max",
    "w_O2_min", "w_O2_max", "w_O2s_min", "w_O2s_max",
    "w_O_min", "w_O_max", "w_Os_min", "w_Os_max",
    "cover_net_surface_current", "cover_electron_primary_flux",
    "cover_O2p_flux", "cover_Om_flux", "cover_Op_flux",
    "cover_surface_charge_total", "cover_sigma_average",
    "cover_sigma_min", "cover_sigma_max", "cover_interface_potential",
]


def expected_times() -> list[float]:
    times = [0.0]
    times.extend(i * 1.0e-9 for i in range(1, 101))
    t = times[-1]
    times.extend(t + i * 1.0e-8 for i in range(1, 91))
    t = times[-1]
    times.extend(t + i * 1.0e-7 for i in range(1, 91))
    t = times[-1]
    times.extend(t + i * 1.0e-6 for i in range(1, 6))
    return times


def close(a: float, b: float, rel: float = 2.0e-5, abs_: float = 1.0e-14) -> bool:
    return abs(a - b) <= max(abs_, rel * max(abs(a), abs(b), 1.0e-300))


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: analyze_cover_15us.py output.csv input.i")

    csv_path = Path(sys.argv[1])
    input_path = Path(sys.argv[2])
    rows = list(csv.DictReader(csv_path.open()))
    if not rows:
        raise SystemExit("empty csv")

    missing = [k for k in REQUIRED if k not in rows[0]]
    if missing:
        raise SystemExit(f"missing CSV columns: {missing}")

    data = [{k: float(row[k]) for k in REQUIRED} for row in rows]
    text = input_path.read_text(encoding="utf-8")
    times = expected_times()

    checks = {}
    checks["row_count_initial_plus_285"] = len(data) == len(times)
    checks["accepted_15us_time_grid"] = len(data) == len(times) and all(
        math.isclose(row["time"], t, rel_tol=0.0, abs_tol=5.0e-15)
        for row, t in zip(data, times)
    )
    checks["final_time_15us"] = math.isclose(
        data[-1]["time"], 1.5e-5, rel_tol=0.0, abs_tol=5.0e-15
    )
    checks["finite_all_steps"] = all(
        all(math.isfinite(v) for v in row.values()) for row in data
    )
    checks["charged_species_positive_all_steps"] = all(
        min(row["ne_min"], row["ni_min"], row["nm_min"], row["nop_min"]) > 0.0
        for row in data
    )
    checks["mean_energy_positive_all_steps"] = all(row["mean_energy_min"] > 0.0 for row in data)
    checks["initial_surface_charge_zero"] = (
        abs(data[0]["cover_surface_charge_total"]) < 1.0e-20
        and abs(data[0]["cover_sigma_average"]) < 1.0e-20
    )

    current_identity = []
    ledger_errors = []
    for i, row in enumerate(data):
        expected_current = E_CHARGE * (
            row["cover_O2p_flux"]
            + row["cover_Op_flux"]
            - row["cover_Om_flux"]
            - row["cover_electron_primary_flux"]
        )
        current_identity.append(
            close(row["cover_net_surface_current"], expected_current, rel=5.0e-8, abs_=1.0e-12)
        )
        if i:
            dt = row["time"] - data[i - 1]["time"]
            dq = row["cover_surface_charge_total"] - data[i - 1]["cover_surface_charge_total"]
            ledger_errors.append(abs(dq - row["cover_net_surface_current"] * dt))

    checks["cover_current_flux_identity_all_steps"] = all(current_identity)
    charge_scale = max(
        [abs(row["cover_surface_charge_total"]) for row in data] + [1.0e-30]
    )
    ledger_tol = max(ABS_Q, REL_Q * charge_scale)
    checks["cover_surface_charge_ledger_all_steps"] = (
        bool(ledger_errors) and max(ledger_errors) <= ledger_tol
    )
    checks["dynamic_surface_charge_active"] = (
        max(abs(row["cover_sigma_average"]) for row in data) > 1.0e-16
    )
    checks["cover_electrostatic_response_finite"] = all(
        math.isfinite(row["cover_interface_potential"]) for row in data
    )

    checks["cover_eps_r_3p6"] = "prop_values = '3.6'" in text and "block = cover" in text
    checks["one_sided_cover_owner"] = all(
        token in text
        for token in (
            "type = SideSetsBetweenSubdomainsGenerator",
            "primary_block = plasma",
            "paired_block = cover",
            "new_boundary = plasma_cover_owner",
            "sidesets = plasma_cover_owner",
        )
    )
    checks["cover_lowerd_sigma_owner"] = (
        text.count("type = PhysicsLowerDSurfaceCurrent") == 1
        and text.count("type = PhysicsADSurfaceChargePoissonBC") == 1
    )
    checks["see_disabled"] = "see_number_flux" not in text and "see_gamma" not in text
    checks["potential_spans_plasma_cover"] = "block = 'plasma cover'" in text

    final = data[-1]
    comparison = {}
    for key, baseline in BASELINE_15US.items():
        pilot = final[key]
        denom = max(abs(baseline), 1.0e-300)
        comparison[key] = {
            "baseline": baseline,
            "cover_15us": pilot,
            "delta": pilot - baseline,
            "relative_delta": (pilot - baseline) / denom,
        }

    result = {
        "classification": (
            "COVER_DIELECTRIC_15US_COMPARISON_PASS"
            if all(checks.values())
            else "COVER_DIELECTRIC_15US_COMPARISON_FAIL"
        ),
        "scope": (
            "Accepted Issue331 contour baseline time grid through 15 us, "
            "cover-only epsilon_r=3.6 ideal-dielectric surface-charge pilot; "
            "SEE=0; no bulk dielectric leakage model."
        ),
        "checks": checks,
        "diagnostics": {
            "final_time_s": final["time"],
            "final_cover_surface_charge_C": final["cover_surface_charge_total"],
            "final_cover_sigma_average_C_m2": final["cover_sigma_average"],
            "final_cover_interface_potential_V": final["cover_interface_potential"],
            "final_cover_net_surface_current_A": final["cover_net_surface_current"],
            "max_surface_ledger_error_C": max(ledger_errors) if ledger_errors else None,
            "surface_ledger_tolerance_C": ledger_tol,
            "baseline_15us_comparison": comparison,
        },
    }

    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
