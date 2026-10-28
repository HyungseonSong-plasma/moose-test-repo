#!/usr/bin/env python3
"""Fail-closed per-arm and four-arm diagnostics for O2+ DR sensitivity runs.

Never turns a numerical/CI success into source-validated scientific parity.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

DR_COLUMNS = (
    "o2p_dr_R_integral",
    "o2p_dr_O_source_integral",
    "o2p_dr_electron_sink_integral",
    "o2p_dr_ion_sink_integral",
    "o2p_dr_energy_sink_integral",
    "o2p_dr_mass_closure_integral",
    "o2p_dr_charge_closure_integral",
)
OBSERVATIONS = (
    "w_O_avg", "w_O_min", "w_O_max", "w_O2_avg",
    "mean_en_solved_avg", "ne_avg", "ni_avg", "w_O2p_avg",
    "P_rf_scaled_W_t6", "P_abs_maxwell_t6", "rf_drive_scale_t6",
)


def number(row: dict[str, str], name: str) -> float | None:
    try:
        value = float(row.get(name, "nan"))
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def rel_ok(actual: float, expected: float, rtol: float = 2e-5) -> bool:
    return math.isclose(actual, expected, rel_tol=rtol, abs_tol=1e-14)


def inspect(result: Path, power: int, mode: str, sha: str, p3: str, p4: str) -> dict:
    csv_file = result / "run" / "plasma.csv"
    rows: list[dict[str, str]] = []
    if csv_file.is_file():
        with csv_file.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    last = rows[-1] if rows else {}
    t = number(last, "time")
    complete = t is not None and t >= 1e-4 - 1e-12
    vals = {key: number(last, key) for key in OBSERVATIONS}
    observed_dr = {key: number(last, key) for key in DR_COLUMNS}
    if mode == "on":
        if all(v is not None for v in observed_dr.values()):
            r, o, e, ion, energy, mass, charge = (observed_dr[k] for k in DR_COLUMNS)
            assert all(v is not None for v in (r, o, e, ion, energy, mass, charge))
            conserved = (
                r >= 0 and rel_ok(o, 0.032 * r)
                and rel_ok(e, -r) and rel_ok(ion, -r)
                and abs(mass) <= 2e-5 * max(abs(o), 1e-12)
                and abs(charge) <= 2e-5 * max(abs(r), 1e-12)
                and energy <= 0
            )
            dr_status = "PASS" if conserved else "FAIL"
        else:
            dr_status = "INCOMPLETE"
    else:
        dr_status = "PASS" if not any(k in last for k in DR_COLUMNS) else "FAIL"

    d1_path = result / "d1_native" / "d1_native_summary.json"
    d1 = json.loads(d1_path.read_text()) if d1_path.is_file() else {}
    d1_ok = (
        d1.get("status") == "D1_NATIVE_DIAGNOSTIC_INTEGRITY_PASS"
        and d1.get("wafer_faces") == 27
        and d1.get("native_points") == 461
    )
    drive, scaled = vals["rf_drive_scale_t6"], vals["P_rf_scaled_W_t6"]
    pid_ok = (
        drive is not None and scaled is not None
        and drive < 3.0 - 1e-6
        and abs(scaled - power) / power <= 0.05
    )
    checks = {
        "full_100us": "PASS" if complete and p3 == "success" else "NOT_PASS",
        "native_27_face_D1": "PASS" if p4 == "success" and d1_ok else "NOT_PASS",
        "rf_power_delivery": "PASS" if complete and pid_ok else "NOT_PASS",
        "dr_source_projection": dr_status,
    }
    return {
        "power_W": power, "dr_mode": mode, "source_sha": sha,
        "last_time_s": t, "csv_rows": len(rows),
        "metrics": vals, "dr_integrals": observed_dr,
        "checks": checks,
        "execution_status": "PASS" if all(v == "PASS" for v in checks.values()) else "NOT_PASS",
        "science_status": "HOLD_RATE_EXTRAPOLATION_PRODUCT_BRANCHING_AND_ENERGY_PROXY",
    }


def compare(cases: list[Path]) -> dict:
    if len(cases) != 4:
        raise ValueError("four per-case JSON reports required")
    records = [json.loads(path.read_text(encoding="utf-8")) for path in cases]
    keyed = {(int(row["power_W"]), row["dr_mode"]): row for row in records}
    if set(keyed) != {(400, "off"), (400, "on"), (1000, "off"), (1000, "on")}:
        raise ValueError("cases must include exactly 400/1000 W each OFF and ON")
    differential: dict[str, dict] = {}
    for power in (400, 1000):
        off, on = keyed[(power, "off")], keyed[(power, "on")]
        metrics = {}
        for key in OBSERVATIONS:
            av, bv = off["metrics"].get(key), on["metrics"].get(key)
            metrics[key] = {
                "off": av, "on": bv,
                "delta": bv-av if av is not None and bv is not None else None,
                "relative_change": (bv-av)/av if av is not None and bv is not None and av != 0 else None,
            }
        differential[str(power)] = {
            "off_execution_status": off["execution_status"],
            "on_execution_status": on["execution_status"],
            "metrics": metrics,
        }
    return {"science_status": "HOLD_RATE_AND_BRANCHING", "differential": differential}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--result", type=Path)
    p.add_argument("--power-w", type=int, choices=[400, 1000])
    p.add_argument("--dr-mode", choices=["off", "on"])
    p.add_argument("--source-sha", default="")
    p.add_argument("--p3-outcome", default="")
    p.add_argument("--p4-outcome", default="")
    p.add_argument("--compare", type=Path, nargs=4)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.compare:
        out = compare(a.compare)
    else:
        if a.result is None or a.power_w is None or a.dr_mode is None:
            p.error("--result, --power-w and --dr-mode required for one arm")
        out = inspect(a.result, a.power_w, a.dr_mode, a.source_sha, a.p3_outcome, a.p4_outcome)
    dest = a.output or (a.result / "diagnostics" / "o2p_dr_ab.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, allow_nan=False))
    return 0 if a.compare or out["execution_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
