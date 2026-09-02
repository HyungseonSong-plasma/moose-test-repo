#!/usr/bin/env python3
from pathlib import Path
import hashlib, os, re, sys

HERE=Path(__file__).resolve().parent
QPX_ROOT=Path(os.environ.get("QPX_ROOT", str(HERE.parents[4]))).resolve()
expected={
  "include/fvkernels/QPXFVConservativeMassFractionTimeDerivative.h": "14dafe844a347dbb423fb437c43004dfe9e4077630e4bdfc1295f7f096692cba",
  "src/fvkernels/QPXFVConservativeMassFractionTimeDerivative.C": "04f1753afdb0fb3a91929ba945d1ec740c2a22f7ab174ae3ce8d40ebae3a54cb"
}

fail=[]
for rel,exp in expected.items():
    p=QPX_ROOT/rel
    if not p.is_file():
        fail.append("missing production source "+str(p))
        continue
    got=hashlib.sha256(p.read_bytes()).hexdigest()
    if got!=exp:
        fail.append(f"source hash mismatch {rel} got={got} expected={exp}")

text=(HERE/"input.i").read_text()
if "scheme = implicit-euler" not in text:
    fail.append("EVR1 exact identity requires scheme = implicit-euler")
if "rho_test" not in text or "expression = '1.0 + t'" not in text:
    fail.append("manufactured rho(t)=1+t contract missing")
if re.search(r"functor_symbols\s*=\s*['\"][^'\"]*\b(?:x|y|z|t|pi|e)\b", text):
    fail.append("reserved parser symbol collision detected")

exe=Path(os.environ.get("QPX_EXECUTABLE", QPX_ROOT/"qpx-opt")).resolve()
if not exe.is_file():
    fail.append("qpx-opt missing: "+str(exe))
else:
    newest=max((QPX_ROOT/rel).stat().st_mtime for rel in expected)
    if exe.stat().st_mtime < newest:
        fail.append("SOURCE_REBUILD_REQUIRED: qpx-opt is older than the new R22 source files")

print("R22_SOURCE_AND_INPUT_PREFLIGHT:", "PASS" if not fail else "FAIL")
for x in fail:
    print("  -",x)
raise SystemExit(0 if not fail else 2)
