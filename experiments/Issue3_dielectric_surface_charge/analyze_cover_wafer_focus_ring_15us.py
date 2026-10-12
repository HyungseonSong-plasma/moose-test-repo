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
OWNERS = ("cover", "wafer", "focus_ring")

BASE_REQUIRED = [
    "time", "charge_integral",
    "ne_min", "ne_max", "ni_min", "ni_max", "nm_min", "nm_max", "nop_min", "nop_max",
    "mean_energy_min", "mean_energy_max", "potential_min", "potential_max",
]
SURFACE_FIELDS = [
    "net_surface_current", "electron_primary_flux", "O2p_flux", "Om_flux", "Op_flux",
    "surface_charge_total", "sigma_average", "sigma_min", "sigma_max", "interface_potential",
]
REQUIRED = BASE_REQUIRED + [
    f"{owner}_{field}" for owner in OWNERS for field in SURFACE_FIELDS
] + ["wafer_ground_potential", "focus_ring_ground_potential"]


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


def named_block(text: str, name: str) -> str:
    header = f"  [{name}]\n"
    start = text.index(header)
    end = text.index("\n  []", start) + len("\n  []")
    return text[start:end]


def surface_diagnostics(data: list[dict[str, float]], owner: str):
    current_identity = []
    ledger_errors = []
    for i, row in enumerate(data):
        expected_current = E_CHARGE * (
            row[f"{owner}_O2p_flux"] + row[f"{owner}_Op_flux"]
            - row[f"{owner}_Om_flux"] - row[f"{owner}_electron_primary_flux"]
        )
        current_identity.append(
            close(row[f"{owner}_net_surface_current"], expected_current, rel=5.0e-8, abs_=1.0e-12)
        )
        if i:
            dt = row["time"] - data[i - 1]["time"]
            dq = row[f"{owner}_surface_charge_total"] - data[i - 1][f"{owner}_surface_charge_total"]
            ledger_errors.append(abs(dq - row[f"{owner}_net_surface_current"] * dt))
    charge_scale = max([abs(row[f"{owner}_surface_charge_total"]) for row in data] + [1.0e-30])
    ledger_tol = max(ABS_Q, REL_Q * charge_scale)
    return {
        "current_identity_all_steps": all(current_identity),
        "ledger_all_steps": bool(ledger_errors) and max(ledger_errors) <= ledger_tol,
        "dynamic_surface_charge_active": max(abs(row[f"{owner}_sigma_average"]) for row in data) > 1.0e-16,
        "interface_potential_finite": all(math.isfinite(row[f"{owner}_interface_potential"]) for row in data),
        "max_ledger_error_C": max(ledger_errors) if ledger_errors else None,
        "ledger_tolerance_C": ledger_tol,
    }


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: analyze_cover_wafer_focus_ring_15us.py output.csv input.i")
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
    surface = {owner: surface_diagnostics(data, owner) for owner in OWNERS}

    checks = {}
    checks["row_count_initial_plus_285"] = len(data) == len(times)
    checks["accepted_15us_time_grid"] = len(data) == len(times) and all(
        math.isclose(row["time"], t, rel_tol=0.0, abs_tol=5.0e-15) for row, t in zip(data, times)
    )
    checks["final_time_15us"] = math.isclose(data[-1]["time"], 1.5e-5, rel_tol=0.0, abs_tol=5.0e-15)
    checks["finite_all_steps"] = all(all(math.isfinite(v) for v in row.values()) for row in data)
    checks["charged_species_positive_all_steps"] = all(
        min(row["ne_min"], row["ni_min"], row["nm_min"], row["nop_min"]) > 0.0 for row in data
    )
    checks["mean_energy_positive_all_steps"] = all(row["mean_energy_min"] > 0.0 for row in data)

    for owner in OWNERS:
        checks[f"initial_{owner}_surface_charge_zero"] = (
            abs(data[0][f"{owner}_surface_charge_total"]) < 1.0e-20
            and abs(data[0][f"{owner}_sigma_average"]) < 1.0e-20
        )
        checks[f"{owner}_current_flux_identity_all_steps"] = surface[owner]["current_identity_all_steps"]
        checks[f"{owner}_surface_charge_ledger_all_steps"] = surface[owner]["ledger_all_steps"]
        checks[f"{owner}_dynamic_surface_charge_active"] = surface[owner]["dynamic_surface_charge_active"]
        checks[f"{owner}_interface_potential_finite"] = surface[owner]["interface_potential_finite"]

    checks["wafer_ground_is_zero_all_steps"] = all(
        abs(row["wafer_ground_potential"]) <= 1.0e-10 for row in data
    )
    checks["focus_ring_ground_is_zero_all_steps"] = all(
        abs(row["focus_ring_ground_potential"]) <= 1.0e-10 for row in data
    )
    checks["cover_eps_r_3p6"] = "prop_values = '3.6'" in named_block(text, "eps_cover")
    checks["wafer_eps_r_12p5"] = "prop_values = '12.5'" in named_block(text, "eps_wafer")
    checks["focus_ring_eps_r_8"] = "prop_values = '8.0'" in named_block(text, "eps_focus_ring")
    checks["potential_spans_all_dielectrics"] = (
        "block = 'plasma cover wafer focus_ring'" in named_block(text, "potential")
        and "block = 'plasma cover wafer focus_ring'" in named_block(text, "phi_diffusion")
    )
    checks["one_sided_cover_owner"] = all(token in text for token in (
        "paired_block = cover", "new_boundary = plasma_cover_owner", "sidesets = plasma_cover_owner", "new_block_name = cover_surface"
    ))
    checks["one_sided_wafer_owner"] = all(token in text for token in (
        "paired_block = wafer", "new_boundary = plasma_wafer_owner", "sidesets = plasma_wafer_owner", "new_block_name = wafer_surface"
    ))
    checks["one_sided_focus_ring_owner"] = all(token in text for token in (
        "paired_block = focus_ring", "new_boundary = plasma_focus_ring_owner", "sidesets = plasma_focus_ring_owner", "new_block_name = focus_ring_surface"
    ))
    checks["three_surface_charge_owners"] = (
        text.count("type = PhysicsLowerDSurfaceCurrent") == 3
        and text.count("type = PhysicsADSurfaceChargePoissonBC") == 3
    )

    ground = named_block(text, "grounded_potential")
    checks["dielectric_ground_routing"] = (
        "wafer_electrode" in ground
        and "focus_ring_ground" in ground
        and "plasma_wafer" not in ground
        and "plasma_focus_ring" not in ground
    )
    energy_sheath = named_block(text, "electron_energy_sheath")
    energy_wafer = named_block(text, "electron_energy_wafer")
    energy_focus = named_block(text, "electron_energy_focus_ring")
    checks["baseline_thermal_energy_law_preserved_on_dielectrics"] = (
        "PhysicsFEMLogMolarElectronEnergyNoSheathSuppressionBC" in energy_sheath
        and "plasma_wafer" not in energy_sheath
        and "plasma_focus_ring" not in energy_sheath
        and "PhysicsFEMLogMolarElectronEnergyDielectricBC" in energy_wafer
        and "boundary = plasma_wafer" in energy_wafer
        and "PhysicsFEMLogMolarElectronEnergyDielectricBC" in energy_focus
        and "boundary = plasma_focus_ring" in energy_focus
    )
    checks["see_disabled"] = "see_number_flux" not in text and "see_gamma" not in text

    final = data[-1]
    diagnostics = {"final_time_s": final["time"]}
    for owner in OWNERS:
        diagnostics[owner] = {
            "surface_charge_C": final[f"{owner}_surface_charge_total"],
            "sigma_average_C_m2": final[f"{owner}_sigma_average"],
            "interface_potential_V": final[f"{owner}_interface_potential"],
            "net_surface_current_A": final[f"{owner}_net_surface_current"],
            "max_ledger_error_C": surface[owner]["max_ledger_error_C"],
            "ledger_tolerance_C": surface[owner]["ledger_tolerance_C"],
        }
    diagnostics["wafer"]["ground_potential_V"] = final["wafer_ground_potential"]
    diagnostics["focus_ring"]["ground_potential_V"] = final["focus_ring_ground_potential"]

    result = {
        "classification": (
            "COVER_WAFER_FOCUS_RING_DIELECTRIC_15US_PASS"
            if all(checks.values())
            else "COVER_WAFER_FOCUS_RING_DIELECTRIC_15US_FAIL"
        ),
        "scope": (
            "Accepted Issue331 15 us time grid; unstructured graded plasma+cover+wafer with canonical QVT solid focus-ring block; "
            "cover eps_r=3.6; wafer eps_r=12.5; focus-ring eps_r=8.0; independent dynamic plasma-side surface charge; "
            "wafer electrode and focus-ring outer boundary grounded at 0 V; baseline thermal electron-energy wall law preserved; "
            "SEE=0; no bulk dielectric-conductivity leakage model."
        ),
        "checks": checks,
        "diagnostics": diagnostics,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
