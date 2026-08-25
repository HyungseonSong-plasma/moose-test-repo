#!/usr/bin/env python3
import csv
import sys
from pathlib import Path


def rel(a, b):
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


if len(sys.argv) != 3:
    raise SystemExit("usage: check_coupling_path.py <csv> <bulk_only|wall_only>")

p = Path(sys.argv[1])
mode = sys.argv[2]

with p.open(newline="") as f:
    rows = list(csv.DictReader(f))

r0 = min(rows, key=lambda r: abs(float(r["time"])))
positive = [r for r in rows if float(r["time"]) > 0]
if not positive:
    raise SystemExit("no positive-time row")
r1 = positive[0]

t0 = float(r0["time"])
t1 = float(r1["time"])
dt = t1 - t0
m0 = float(r0["ion_mass_inventory"])
m1 = float(r1["ion_mass_inventory"])
dm = m1 - m0
phi_min = float(r1["phi_min"])
phi_max = float(r1["phi_max"])

print(f"mode                               = {mode}")
print(f"time step                          = {dt:.12e}")
print(f"mass m0/m1                         = {m0:.12e} / {m1:.12e}")
print(f"mass change dm                     = {dm:.12e}")
print(f"phi min/max                        = {phi_min:.12e} / {phi_max:.12e}")

if mode == "bulk_only":
    q0 = float(r0["ion_mass_first_moment"])
    q1 = float(r1["ion_mass_first_moment"])
    c0 = q0 / m0
    c1 = q1 / m1
    mass_error = rel(m1, m0)

    print(f"mass conservation rel error        = {mass_error:.6e}")
    print(f"centroid x0/x1                     = {c0:.12e} / {c1:.12e}")
    print(f"centroid shift                     = {c1-c0:.12e}")

    ok = (
        mass_error < 1e-10
        and c1 > c0
        and phi_max > phi_min
    )

elif mode == "wall_only":
    lm = float(r1["left_migration_mass_loss_rate"])
    rm = float(r1["right_migration_mass_loss_rate"])
    mig = lm + rm
    balance_error = rel(dm, -mig * dt)

    print(f"left migration loss rate           = {lm:.12e}")
    print(f"right migration loss rate          = {rm:.12e}")
    print(f"expected mass change               = {-mig*dt:.12e}")
    print(f"wall migration balance rel error   = {balance_error:.6e}")

    ok = (
        rm > 0
        and abs(lm) < 1e-30
        and balance_error < 1e-8
        and phi_max > phi_min
    )

else:
    raise SystemExit(f"unknown mode: {mode}")

print("\nOVERALL:", "PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
