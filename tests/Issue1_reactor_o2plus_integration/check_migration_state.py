#!/usr/bin/env python3
import csv
import sys
from pathlib import Path

if len(sys.argv) < 2:
    raise SystemExit("usage: check_migration_state.py <csv> [migration_only|full]")
p = Path(sys.argv[1])
mode = sys.argv[2] if len(sys.argv) > 2 else "migration_only"
with p.open(newline="") as f:
    rows = list(csv.DictReader(f))
r0 = min(rows, key=lambda r: abs(float(r["time"])-0.0))
positive = [r for r in rows if float(r["time"]) > 0]
if not positive:
    raise SystemExit("no positive-time row")
r1 = positive[0]
dt = float(r1["time"]) - float(r0["time"])
dm = float(r1["ion_mass_inventory"]) - float(r0["ion_mass_inventory"])
ls = float(r1["left_surface_mass_loss_rate"])
rs = float(r1["right_surface_mass_loss_rate"])
lm = float(r1["left_migration_mass_loss_rate"])
rm = float(r1["right_migration_mass_loss_rate"])
surf = ls+rs
mig = lm+rm
wall = surf+mig
def rel(a,b):
    return abs(a-b)/max(abs(a),abs(b),1e-300)
print(f"time step                          = {dt:.12e}")
print(f"mass change dm                     = {dm:.12e}")
print(f"surface loss rate                  = {surf:.12e}")
print(f"migration loss rate                = {mig:.12e}")
print(f"total wall loss rate               = {wall:.12e}")
print(f"dm vs surface-only rel error       = {rel(dm,-surf*dt):.6e}")
print(f"dm vs migration-only rel error     = {rel(dm,-mig*dt):.6e}")
print(f"dm vs total-wall rel error         = {rel(dm,-wall*dt):.6e}")
print(f"right migration rate               = {rm:.12e}")
print(f"left migration rate                = {lm:.12e}")
if mode == "migration_only":
    ok = abs(surf) < 1e-30 and rm > 0 and abs(lm) < 1e-30 and rel(dm,-mig*dt) < 1e-8
else:
    ok = rm > 0 and abs(lm) < 1e-30 and rel(dm,-wall*dt) < 1e-8
print("\nOVERALL:", "PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
