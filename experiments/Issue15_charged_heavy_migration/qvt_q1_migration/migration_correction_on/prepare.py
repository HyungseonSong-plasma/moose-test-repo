#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent
exp=json.loads((HERE/"expected.json").read_text())
t=(HERE/"physics.i").read_text()
fail=[]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
for fn,key in [("qvt.msh","source_qvt_sha256"),("transport_data.txt","source_transport_data_sha256"),
               ("physics.i","physics_sha256"),("input.i","input_sha256")]:
    if sha(HERE/fn)!=exp[key]: fail.append(fn+" hash mismatch")
dc=t.count("type = QPXFVElectrostaticDrift")
cc=t.count("type = QPXFVHeavyMassElectromigrationCorrection")
if exp["direct_migration"] and dc!=3: fail.append(f"expected 3 drift kernels, got {dc}")
if not exp["direct_migration"] and dc!=0: fail.append("migration-off contains drift")
if exp["correction"] and cc!=6: fail.append(f"expected 6 correction kernels, got {cc}")
if not exp["correction"] and cc!=0: fail.append("correction-off contains correction")
for tok in ["heavy_mass_correction_velocity","ion_drift_velocity_","u_slip =","v_slip =","w_slip ="]:
    if tok in t: fail.append("Path-B exclusivity "+tok)
if "variable = w_O2\n" in t: fail.append("O2 must remain constrained")
if exp["correction"] and "ion_charges = '1 -1 1'" not in t: fail.append("charge order")
if "expression = '-${E0_migration}*x'" not in t: fail.append("prescribed potential")
if t.count("1.602176634e-19*dmix_i/(1.380649e-23*temp_i)") != 3: fail.append("Einstein mobility contract")
reserved={"x","y","z","t","pi","e"}
for raw in re.findall(r"functor_symbols\s*=\s*'([^']+)'",t):
    bad=reserved.intersection(raw.split())
    if bad: fail.append("reserved aliases "+str(sorted(bad)))
print("R15_EVR2_STATIC_P0:", "PASS" if not fail else "FAIL")
if fail:
    for x in fail: print("  -",x)
    raise SystemExit(2)
