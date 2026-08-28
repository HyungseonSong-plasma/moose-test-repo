#!/usr/bin/env python3
import sys
from pathlib import Path

REQUIRED = (
    "type = QPXPlasmaChargeDensityMaterial",
    "type = FVDiffusion",
    "type = FVCoupledForce",
    "v = poisson_charge_source",
    "coeff = relative_permittivity",
    "type = FVDirichletBC",
)
FORBIDDEN = ("ParsedFunctorMaterial", "ADParsedFunctorMaterial")

def check(path):
    s=Path(path).read_text()
    missing=[x for x in REQUIRED if x not in s]
    forbidden=[x for x in FORBIDDEN if x in s]
    ok=not missing and not forbidden and s.count("[phi_charge_source]")==1 and s.count("[phi_diffusion]")==1
    print(f"P1_STATIC {Path(path).parent.name}: " + ("PASS" if ok else "FAIL"))
    if missing: print("  missing="+repr(missing))
    if forbidden: print("  forbidden="+repr(forbidden))
    return ok

if __name__=="__main__":
    ok=all(check(p) for p in sys.argv[1:])
    raise SystemExit(0 if ok else 1)
