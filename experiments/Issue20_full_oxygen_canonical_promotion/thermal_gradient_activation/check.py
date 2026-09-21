#!/usr/bin/env python3
from __future__ import annotations
import csv, json, math, sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit("usage: check.py input_out.csv prepare_evidence.json")

csv_path = Path(sys.argv[1])
ev_path = Path(sys.argv[2])
fail = []

if not ev_path.is_file():
    fail.append("missing prepare_evidence.json")
else:
    ev = json.loads(ev_path.read_text())
    if ev.get("status") != "PASS":
        fail.append(f"prepare status is {ev.get('status')}")
    if ev.get("failures"):
        fail.append(f"prepare failures: {ev.get('failures')}")

if not csv_path.is_file():
    fail.append(f"missing runtime CSV: {csv_path}")
    rows = []
else:
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        fail.append("runtime CSV has no rows")

def val(row, name):
    try:
        x = float(row[name])
    except Exception as e:
        fail.append(f"missing/non-numeric {name}: {e}")
        return float("nan")
    if not math.isfinite(x):
        fail.append(f"non-finite {name}: {x}")
    return x

if rows:
    r = rows[-1]

    Tg_min = val(r, "T_grad_min")
    Tg_max = val(r, "T_grad_max")
    Tf_min = val(r, "T_flat_min")
    Tf_max = val(r, "T_flat_max")

    DTg_min = val(r, "DT_grad_O_min")
    DTg_max = val(r, "DT_grad_O_max")
    DTf_min = val(r, "DT_flat_O_min")
    DTf_max = val(r, "DT_flat_O_max")

    on_min = val(r, "probe_grad_on_min")
    on_max = val(r, "probe_grad_on_max")
    on_avg = val(r, "probe_grad_on_avg")
    off_min = val(r, "probe_grad_off_min")
    off_max = val(r, "probe_grad_off_max")
    flat_min = val(r, "probe_flat_on_min")
    flat_max = val(r, "probe_flat_on_max")

    print(f"T_grad=[{Tg_min:.17e},{Tg_max:.17e}] range={Tg_max-Tg_min:.9e}")
    print(f"T_flat=[{Tf_min:.17e},{Tf_max:.17e}] range={Tf_max-Tf_min:.9e}")
    print(f"DT_grad_O=[{DTg_min:.17e},{DTg_max:.17e}]")
    print(f"DT_flat_O=[{DTf_min:.17e},{DTf_max:.17e}]")
    print(f"probe_grad_on=[{on_min:.17e},{on_max:.17e}] avg={on_avg:.17e}")
    print(f"probe_grad_off=[{off_min:.17e},{off_max:.17e}]")
    print(f"probe_flat_on=[{flat_min:.17e},{flat_max:.17e}]")

    if Tg_max - Tg_min < 200.0:
        fail.append("nonlinear temperature profile did not establish a material gradient")
    if abs(Tf_min - 600.0) > 1e-10 or abs(Tf_max - 600.0) > 1e-10:
        fail.append("flat-temperature negative control is not 600 K")

    dt_signal = max(abs(DTg_min), abs(DTg_max))
    if not dt_signal > 1e-10:
        fail.append(f"production D_T,O is not materially nonzero: {dt_signal}")

    signal = max(abs(on_min), abs(on_max))
    off_control = max(abs(off_min), abs(off_max))
    flat_control = max(abs(flat_min), abs(flat_max))

    print(f"THERMAL_SIGNAL={signal:.9e}")
    print(f"SWITCH_OFF_CONTROL={off_control:.9e}")
    print(f"ZERO_GRAD_CONTROL={flat_control:.9e}")

    if signal <= 1e-12:
        fail.append(f"thermal-gradient ON signal is too small: {signal}")

    control_tol = max(1e-12, signal * 1e-6)
    print(f"CONTROL_TOL={control_tol:.9e}")

    if off_control > control_tol:
        fail.append(
            f"include_thermal_diffusion=false did not suppress response: "
            f"{off_control} > {control_tol}"
        )
    if flat_control > control_tol:
        fail.append(
            f"grad(T)=0 did not suppress thermal response: "
            f"{flat_control} > {control_tol}"
        )

    if signal > 0:
        print(f"ON_OFF_DISCRIMINATION={signal/max(off_control,1e-300):.9e}")
        print(f"GRAD_ZERO_DISCRIMINATION={signal/max(flat_control,1e-300):.9e}")

print("="*78)
if fail:
    print("R14_EVR1C_THERMAL_GRADIENT_ACTIVATION: FAIL")
    for x in fail:
        print("  -",x)
    raise SystemExit(1)

print("R14_EVR1C_THERMAL_GRADIENT_ACTIVATION: PASS")
print("EVR_CREDIT: NONE — EVR1-C tranche only; parent EVR1 not yet accepted")
