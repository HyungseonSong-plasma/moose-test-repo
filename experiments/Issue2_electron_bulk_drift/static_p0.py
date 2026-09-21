#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, re, subprocess, sys

HERE=Path(__file__).resolve().parent
CASES=['diffusion_only', 'drift_Eplus', 'drift_Eminus', 'drift_zero', 'combined', 'qvt_prepoisson']
TABLE_SHA="994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387"
fail=[]

for name in CASES:
    d=HERE/name
    for req in ["input.i","electron_moments.txt","expected.json","test.json"]:
        if not (d/req).is_file():
            fail.append(f"{name}: missing {req}")
    if name=="qvt_prepoisson" and not (d/"qvt.msh").is_file():
        fail.append("qvt_prepoisson: missing qvt.msh")
    if fail and not (d/"input.i").is_file():
        continue

    t=(d/"input.i").read_text()
    cfg=json.loads((d/"test.json").read_text())
    exp=json.loads((d/"expected.json").read_text())

    if cfg.get("validation_schema") != 2:
        fail.append(f"{name}: validation_schema != 2")
    specs=cfg.get("temporal_csv",[])
    if len(specs)!=1 or specs[0].get("initial_row_policy")!="exclude_observation":
        fail.append(f"{name}: temporal exclude_observation missing")
    if "input_out.physical.csv" not in [str(x) for x in cfg.get("checker_args",[])]:
        fail.append(f"{name}: checker not routed to physical CSV")

    h=hashlib.sha256((d/"electron_moments.txt").read_bytes()).hexdigest()
    if h != TABLE_SHA:
        fail.append(f"{name}: electron table SHA mismatch {h}")

    if t.count("type = QPXElectronTransportLookupMaterial") != 1:
        fail.append(f"{name}: expected exactly one QPXElectronTransportLookupMaterial")
    if "property_table_file = electron_moments.txt" not in t:
        fail.append(f"{name}: lookup not wired to case-local electron_moments.txt")
    if "type = ElectronTransportCoefficients" in t or "QPXElectronTransportCoefficients" in t:
        fail.append(f"{name}: legacy log-density transport path present")
    if t.count("type = FVTimeKernel") != 1:
        fail.append(f"{name}: expected one FVTimeKernel")

    needs_diff=exp["mode"] in ("diffusion","combined","qvt")
    diff_count=t.count("type = FVDiffusion")
    if needs_diff and diff_count != 1:
        fail.append(f"{name}: expected one electron FVDiffusion")
    if not needs_diff and diff_count != 0:
        fail.append(f"{name}: drift discriminator unexpectedly contains diffusion")
    if needs_diff and "coeff = electron_diffusion" not in t:
        fail.append(f"{name}: FVDiffusion not wired to electron_diffusion")

    needs_drift=exp["mode"] in ("drift","combined","qvt")
    drift_count=t.count("type = QPXFVElectrostaticDrift")
    if needs_drift and drift_count != 1:
        fail.append(f"{name}: expected one QPXFVElectrostaticDrift")
    if not needs_drift and drift_count != 0:
        fail.append(f"{name}: diffusion-only contains drift")
    if needs_drift:
        for tok in [
          "mobility = electron_mobility",
          "carrier = carrier_one",
          "charge_number = -1",
          "advected_interp_method = upwind",
          "boundaries_to_avoid ="
        ]:
            if tok not in t:
                fail.append(f"{name}: missing drift contract {tok}")

    forbidden=["FVCoupledForce","QPXPlasmaChargeDensityMaterial","poisson_charge_source"]
    for tok in forbidden:
        if tok in t:
            fail.append(f"{name}: Poisson feedback token forbidden in #2: {tok}")

    # Machine gate for parsed-functor aliases; none are expected here.
    for raw_alias in re.findall(r"functor_symbols\s*=\s*'([^']+)'",t):
        bad={"x","y","z","t","pi","e"}.intersection(raw_alias.split())
        if bad:
            fail.append(f"{name}: reserved parser aliases {sorted(bad)}")

# Table schema/range/exact-row source parity.
rows=[]
for ln in (HERE/"diffusion_only/electron_moments.txt").read_text().splitlines():
    cols=ln.split()
    if len(cols)!=3:
        fail.append("electron table: non-3-column row")
        continue
    rows.append(tuple(map(float,cols)))
if not rows or abs(rows[0][0]-1.40991)>1e-12 or abs(rows[-1][0]-22.1378)>1e-12:
    fail.append("electron table: audited range mismatch")
if not any(abs(a-5.73276)<1e-12 and abs(b-1.57e24)/1.57e24<1e-12 and abs(c-6.64e24)/6.64e24<1e-12 for a,b,c in rows):
    fail.append("electron table: EVR1 exact row missing")

for cmd,label in [
  ([sys.executable,str(HERE/"check_case.py"),"--self-test"],"case checker"),
  ([sys.executable,str(HERE/"compare.py"),"--self-test"],"cross checker"),
]:
    p=subprocess.run(cmd,cwd=HERE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    print(p.stdout,end="")
    if p.returncode!=0:
        fail.append(label+" self-test failed")

print("R2_STATIC_P0:", "PASS" if not fail else "FAIL")
if fail:
    for x in fail:
        print("  -",x)
    raise SystemExit(2)
