#!/usr/bin/env python3
from __future__ import annotations
import csv, json, math, sys
from pathlib import Path

R = 8.31446
P = 13.332
T = 600.0
EOS_SCALE = P/(R*T)

SPECIES = ["O2","O2s","O2p","O","Om","Op","Os"]
SOLVED = ["O2s","O2p","O","Om","Op","Os"]

MASS_TOL = 2.0e-10
BOUND_TOL = 2.0e-10
EOS_REL_TOL = 2.0e-9
CHAIN_REL_TOL = 2.0e-9
INVMN_FD_REL_TOL = 2.0e-7

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
        fail.append(f"prepare contains failures: {ev.get('failures')}")

if not csv_path.is_file():
    fail.append(f"missing runtime CSV: {csv_path}")
    rows = []
else:
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        fail.append("runtime CSV has no rows")

def get(row, name):
    try:
        v = float(row[name])
    except Exception as e:
        fail.append(f"missing/non-numeric {name}: {e}")
        return float("nan")
    if not math.isfinite(v):
        fail.append(f"non-finite {name}: {v}")
    return v

physical = []
for row in rows:
    try:
        tm = float(row.get("time", "nan"))
    except Exception:
        continue
    if math.isfinite(tm) and tm > 0.0:
        physical.append(row)

if len(physical) < 3:
    fail.append(f"need >=3 physical timestep rows, got {len(physical)}")

max_mass_error = 0.0
max_eos_rel = 0.0
max_chain_rel = 0.0
max_invMn_fd_rel = 0.0
max_mn_secant_rel = 0.0
max_rho_secant_rel = 0.0
max_drho_signal = 0.0
max_dmn_signal = 0.0
max_species_dot_signal = 0.0
max_invMn_dot_signal = 0.0

for row in physical:
    tm = get(row, "time")

    for s in SOLVED:
        lo = get(row, f"w_{s}_min")
        hi = get(row, f"w_{s}_max")
        if lo < -BOUND_TOL or hi > 1.0 + BOUND_TOL:
            fail.append(f"{s} bounds fail at t={tm}: [{lo},{hi}]")

    o2_lo = get(row, "w_O2_min")
    o2_hi = get(row, "w_O2_max")
    if o2_lo < -BOUND_TOL or o2_hi > 1.0 + BOUND_TOL:
        fail.append(f"constrained O2 bounds fail at t={tm}: [{o2_lo},{o2_hi}]")

    sw_lo = get(row, "sum_w_min")
    sw_hi = get(row, "sum_w_max")
    mass_err = max(abs(sw_lo-1.0), abs(sw_hi-1.0))
    max_mass_error = max(max_mass_error, mass_err)
    if mass_err > MASS_TOL:
        fail.append(f"mass closure fail at t={tm}: [{sw_lo},{sw_hi}]")

    mn_avg = get(row, "Mn_avg")
    mn_lo = get(row, "Mn_min")
    mn_hi = get(row, "Mn_max")
    if mn_lo < 0.016 - 1e-12 or mn_hi > 0.032 + 1e-12:
        fail.append(f"Mn bounds fail at t={tm}: [{mn_lo},{mn_hi}]")

    invmn_lo = get(row, "invMn_min")
    invmn_hi = get(row, "invMn_max")
    if invmn_lo <= 0.0 or invmn_hi <= 0.0:
        fail.append(f"1/Mn positivity fail at t={tm}: [{invmn_lo},{invmn_hi}]")

    rho_avg = get(row, "rho_avg")
    rho_lo = get(row, "rho_min")
    rho_hi = get(row, "rho_max")
    if rho_lo <= 0.0 or rho_hi <= 0.0:
        fail.append(f"rho positivity fail at t={tm}: [{rho_lo},{rho_hi}]")

    for label, rho_v, mn_v in [
        ("avg", rho_avg, mn_avg),
        ("min", rho_lo, mn_lo),
        ("max", rho_hi, mn_hi),
    ]:
        expected = EOS_SCALE * mn_v
        rel = abs(rho_v-expected)/max(abs(expected),1e-300)
        max_eos_rel = max(max_eos_rel, rel)
        if rel > EOS_REL_TOL:
            fail.append(f"EOS {label} parity fail at t={tm}: rel={rel:.3e}")

    dmn = get(row, "dMn_dt_avg")
    drho = get(row, "drho_dt_avg")

    max_dmn_signal = max(max_dmn_signal, abs(dmn))
    max_drho_signal = max(max_drho_signal, abs(drho))
    invmn_dot = get(row, "invMn_dot_avg")
    max_invMn_dot_signal = max(max_invMn_dot_signal, abs(invmn_dot))

    # Independent reconstruction from CURRENT direct TimeDerivativeAux averages.
    # Because S=1/Mn is linear in composition:
    #   Sdot = 31.25*(Ydot_O + Ydot_Om + Ydot_Op + Ydot_Os).
    sdot_from_direct = 31.25 * (
        get(row, "dw_O_avg")
        + get(row, "dw_Om_avg")
        + get(row, "dw_Op_avg")
        + get(row, "dw_Os_avg")
    )
    sdot_rel = abs(invmn_dot-sdot_from_direct) / max(
        abs(invmn_dot), abs(sdot_from_direct), 1e-12
    )
    if sdot_rel > CHAIN_REL_TOL:
        fail.append(
            f"invMn_dot functor/direct-dYdt mismatch at t={tm}: rel={sdot_rel:.3e}"
        )

    expected_drho = EOS_SCALE * dmn
    rel = abs(drho-expected_drho)/max(abs(drho),abs(expected_drho),1e-14)
    max_chain_rel = max(max_chain_rel, rel)
    if rel > CHAIN_REL_TOL:
        fail.append(f"drho/dt chain identity fail at t={tm}: rel={rel:.3e}")

    species_dot = max(
        abs(get(row, "dw_O_dt_min")),
        abs(get(row, "dw_O_dt_max")),
        abs(get(row, "dw_Os_dt_min")),
        abs(get(row, "dw_Os_dt_max")),
    )
    max_species_dot_signal = max(max_species_dot_signal, species_dot)

    for s in SPECIES:
        d = get(row, f"Dmix_{s}_avg")
        if not (math.isfinite(d) and d > 0.0):
            fail.append(f"D_mix_{s} invalid at t={tm}: {d}")

# Exact discrete temporal gate on S = 1/Mn.
# invMn_dot_avg is now evaluated directly in the postprocessor stage after the
# TimeDerivativeAux kernels update dw_k/dt. S is linear in Q-1 composition, so
# BE finite difference must match to solver/output precision.
for prev, cur in zip(physical[:-1], physical[1:]):
    t0 = get(prev, "time")
    t1 = get(cur, "time")
    dt = t1 - t0
    if not dt > 0:
        fail.append(f"non-positive CSV dt: {dt}")
        continue

    s0 = get(prev, "invMn_avg")
    s1 = get(cur, "invMn_avg")
    sdot_fd = (s1-s0)/dt
    sdot_model = get(cur, "invMn_dot_avg")
    srel = abs(sdot_fd-sdot_model)/max(abs(sdot_fd),abs(sdot_model),1e-12)
    max_invMn_fd_rel = max(max_invMn_fd_rel, srel)

    print(
        f"INVMN_FD t={t1:.7g} fd={sdot_fd:.17e} "
        f"model={sdot_model:.17e} rel={srel:.6e}"
    )

    if abs(sdot_fd) > 1e-12 and abs(sdot_model) > 1e-12 and sdot_fd*sdot_model < 0:
        fail.append(f"1/Mn derivative sign mismatch at t={t1}")
    if srel > INVMN_FD_REL_TOL:
        fail.append(f"1/Mn finite-difference parity fail t={t1}: rel={srel:.3e}")

    # Diagnostic-only nonlinear secant comparison.
    mn0 = get(prev, "Mn_avg")
    mn1 = get(cur, "Mn_avg")
    rho0 = get(prev, "rho_avg")
    rho1 = get(cur, "rho_avg")
    mn_fd = (mn1-mn0)/dt
    rho_fd = (rho1-rho0)/dt
    dmn = get(cur, "dMn_dt_avg")
    drho = get(cur, "drho_dt_avg")

    mn_rel = abs(mn_fd-dmn)/max(abs(mn_fd),abs(dmn),1e-14)
    rho_rel = abs(rho_fd-drho)/max(abs(rho_fd),abs(drho),1e-14)
    max_mn_secant_rel = max(max_mn_secant_rel, mn_rel)
    max_rho_secant_rel = max(max_rho_secant_rel, rho_rel)

if max_species_dot_signal <= 1e-8:
    fail.append(f"direct solved-species time-derivative activity too small: {max_species_dot_signal}")
if max_invMn_dot_signal <= 1e-6:
    fail.append(f"1/Mn derivative activity too small: {max_invMn_dot_signal}")
if max_dmn_signal <= 1e-10:
    fail.append(f"chain-rule dMn/dt activity too small: {max_dmn_signal}")
if max_drho_signal <= 1e-12:
    fail.append(f"chain-rule drho/dt activity too small: {max_drho_signal}")

print(f"PHYSICAL_ROWS={len(physical)}")
print(f"MAX_MASS_CLOSURE_ERROR={max_mass_error:.9e}")
print(f"MAX_EOS_REL_ERROR={max_eos_rel:.9e}")
print(f"MAX_DRHO_CHAIN_REL_ERROR={max_chain_rel:.9e}")
print(f"MAX_INVMN_FD_REL_ERROR={max_invMn_fd_rel:.9e}")
print("DERIVED_EVALUATION_STAGE=POSTPROCESSOR_AFTER_DWDT_AUX")
print(f"DIAGNOSTIC_MAX_MN_SECANT_REL_ERROR={max_mn_secant_rel:.9e}")
print(f"DIAGNOSTIC_MAX_RHO_SECANT_REL_ERROR={max_rho_secant_rel:.9e}")
print(f"MAX_DIRECT_SPECIES_DY_DT={max_species_dot_signal:.9e}")
print(f"MAX_ABS_INVMN_DOT={max_invMn_dot_signal:.9e}")
print(f"MAX_ABS_DMN_DT={max_dmn_signal:.9e}")
print(f"MAX_ABS_DRHO_DT={max_drho_signal:.9e}")
print("="*78)

if fail:
    print("R14_EVR1D_TRANSIENT_MIXTURE_STATE: FAIL")
    for x in fail:
        print("  -", x)
    raise SystemExit(1)

print(f"INVMN_FD_REL_TOL={INVMN_FD_REL_TOL:.1e}")
print("R14_EVR1D_TRANSIENT_MIXTURE_STATE: PASS")
print("EVR_CREDIT: NONE — EVR1-D tranche only; parent EVR1 requires Validator acceptance")
