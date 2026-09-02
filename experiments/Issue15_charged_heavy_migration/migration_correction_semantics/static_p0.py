#!/usr/bin/env python3
from pathlib import Path
import json, re, subprocess, sys

HERE=Path(__file__).resolve().parent
CASES=[
 "migration_off","migration_on_Eplus","migration_on_Eminus",
 "migration_on_zminus","migration_on_mu2","correction_off"
]
fail=[]

for name in CASES:
    d=HERE/name
    t=(d/"input.i").read_text()
    cfg=json.loads((d/"test.json").read_text())
    exp=json.loads((d/"expected.json").read_text())

    if cfg.get("validation_schema") != 2:
        fail.append(f"{name}: validation_schema=2 missing")
    specs=cfg.get("temporal_csv",[])
    if len(specs)!=1 or specs[0].get("initial_row_policy")!="exclude_observation":
        fail.append(f"{name}: temporal row contract missing")
    if "input_out.physical.csv" not in [str(x) for x in cfg.get("checker_args",[])]:
        fail.append(f"{name}: checker not routed to physical CSV")

    # #22 accumulation remains frozen/used.
    if t.count("type = QPXFVConservativeMassFractionTimeDerivative") != 2:
        fail.append(f"{name}: expected two conservative time kernels")

    # Direct drift is ion-only whenever enabled.
    direct_count=t.count("type = QPXFVElectrostaticDrift")
    if exp["direct"] and direct_count != 1:
        fail.append(f"{name}: expected exactly one direct drift kernel")
    if not exp["direct"] and direct_count != 0:
        fail.append(f"{name}: migration OFF contains direct drift")
    if re.search(r"type\s*=\s*QPXFVElectrostaticDrift[\s\S]{0,180}variable\s*=\s*w_neutral",t):
        fail.append(f"{name}: neutral must not receive direct electrostatic drift")

    corr_count=t.count("type = QPXFVHeavyMassElectromigrationCorrection")
    if exp["correction"] and corr_count != 2:
        fail.append(f"{name}: expected ion+neutral correction kernels")
    if not exp["correction"] and corr_count != 0:
        fail.append(f"{name}: correction-OFF contains correction kernel")

    # Path-B exclusivity: do not mix slip-velocity migration into bulk advection.
    forbidden=[
      "heavy_mass_correction_velocity",
      "ion_drift_velocity_",
      "u_slip =",
      "v_slip =",
      "w_slip =",
    ]
    for tok in forbidden:
        if tok in t:
            fail.append(f"{name}: Path-B double-count risk token present: {tok}")

    # Exact production parameter contract from audited source/wiring.
    if exp["direct"]:
        for tok in ["potential = phi","mobility = mobility","carrier = rho",
                    "advected_interp_method = upwind","boundaries_to_avoid = 'left right'"]:
            if tok not in t:
                fail.append(f"{name}: missing direct-drift parameter {tok}")
    if exp["correction"]:
        for tok in ["potential = phi","rho = rho","ion_mass_fractions = 'w_ion'",
                    "ion_mobilities = 'mobility'",
                    "advected_interp_method = upwind","boundaries_to_avoid = 'left right'"]:
            if tok not in t:
                fail.append(f"{name}: missing correction parameter {tok}")

    # Parser aliases must avoid reserved x,y,z,t,pi,e.
    for raw in re.findall(r"functor_symbols\s*=\s*'([^']+)'",t):
        bad={"x","y","z","t","pi","e"}.intersection(raw.split())
        if bad:
            fail.append(f"{name}: reserved parser aliases {sorted(bad)}")

# Cross checker and single-case checker self-tests are part of P0.
for cmd,label in [
    ([sys.executable,str(HERE/"check_case.py"),"--self-test"],"case checker"),
    ([sys.executable,str(HERE/"compare.py"),"--self-test"],"cross checker"),
]:
    p=subprocess.run(cmd,cwd=HERE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    print(p.stdout,end="")
    if p.returncode!=0:
        fail.append(label+" self-test failed")

print("R15_PATH_B_STATIC_P0:", "PASS" if not fail else "FAIL")
if fail:
    for x in fail:
        print("  -",x)
    raise SystemExit(2)
