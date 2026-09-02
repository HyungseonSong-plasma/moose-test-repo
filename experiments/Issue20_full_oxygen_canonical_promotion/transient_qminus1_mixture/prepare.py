#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import hashlib, json, os, subprocess, sys

CASE = Path(__file__).resolve().parent
QPX = Path(os.environ["QPX_ROOT"]).resolve()
INPUT = CASE / "input.i"
DB = CASE / "transport_data.txt"

C = QPX / "src" / "materials" / "QPXThermalDiffusionMaterial.C"
H = QPX / "include" / "materials" / "QPXThermalDiffusionMaterial.h"

EXPECTED_C = "4533a3a2fe0d77f3d85ca171f9093907a76514dd024c5392c08dd8d17a2f4b7e"
EXPECTED_H = "8f97db663781c5788e18bb98cca284a9173597a2b7bfe44f148ca2beef9391c5"
EXPECTED_DB = "2fa7988c79f6ea23ebdd50e6d1d7fc5018dc8854a27459511ec95c94ebe7ff3d"

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def find_prod(name):
    found = []
    for p in QPX.rglob(name):
        try:
            rel = p.resolve().relative_to(QPX)
        except Exception:
            continue
        if "temp" in rel.parts:
            continue
        found.append(p.resolve())
    return found

fail = []

print(f"CONDA_PREFIX={os.environ.get('CONDA_PREFIX','')}")
print(f"CONDA_DEFAULT_ENV={os.environ.get('CONDA_DEFAULT_ENV','')}")
if not os.environ.get("CONDA_PREFIX"):
    print("R14_EVR1D_ENV_WARNING: CONDA_PREFIX is empty; prior local ADParser JIT recurrence was observed without conda activation")

for label, p, exp in [("C", C, EXPECTED_C), ("H", H, EXPECTED_H), ("DB", DB, EXPECTED_DB)]:
    if not p.is_file():
        fail.append(f"missing {label}: {p}")
        continue
    got = sha(p)
    print(f"{label}_SHA256={got}")
    if got != exp:
        fail.append(f"{label} hash mismatch")

# P0 case contract and mutation controls.
for cmd, label in [
    ([sys.executable, str(CASE/"validate_case.py"), "--self-test"], "P0 mutation self-test"),
    ([sys.executable, str(CASE/"validate_case.py"), str(INPUT)], "P0 static contract"),
    ([sys.executable, str(CASE/"oracle.py")], "algebra oracle self-test"),
]:
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        fail.append(label + " failed")

# Production source-contract checks for the two species kernels used here.
time_srcs = find_prod("QPXFVMassFractionTimeDerivative.C")
diff_srcs = find_prod("QPXFVMixtureAveragedDiffusion.C")

if len(time_srcs) != 1:
    fail.append(f"expected one production QPXFVMassFractionTimeDerivative.C; found {len(time_srcs)}")
else:
    s = time_srcs[0].read_text(errors="replace")
    print(f"TIME_KERNEL_SOURCE={time_srcs[0]}")
    for token in [
        'registerADMooseObject("qpxApp", QPXFVMassFractionTimeDerivative)',
        '"rho"',
        'return rho * _u_dot[_qp];',
    ]:
        if token not in s:
            fail.append(f"time-kernel source contract missing: {token}")

if len(diff_srcs) != 1:
    fail.append(f"expected one production QPXFVMixtureAveragedDiffusion.C; found {len(diff_srcs)}")
else:
    s = diff_srcs[0].read_text(errors="replace")
    print(f"DIFF_KERNEL_SOURCE={diff_srcs[0]}")
    for token in [
        'registerMooseObject("qpxApp", QPXFVMixtureAveragedDiffusion)',
        '"rho"',
        '"diffusivity"',
        '"mean_molar_mass"',
        '"include_molar_mass_gradient"',
        '(dwdn + (w_face / Mn_face) * dMndn)',
    ]:
        if token not in s:
            fail.append(f"mixture-diffusion source contract missing: {token}")

evidence = {
    "status": "PASS" if not fail else "FAIL",
    "classification": "R14_EVR1D_TRANSIENT_MIXTURE_PREFLIGHT",
    "material_c_sha256": sha(C) if C.is_file() else None,
    "material_h_sha256": sha(H) if H.is_file() else None,
    "transport_data_sha256": sha(DB) if DB.is_file() else None,
    "time_kernel_source": str(time_srcs[0]) if len(time_srcs)==1 else None,
    "diffusion_kernel_source": str(diff_srcs[0]) if len(diff_srcs)==1 else None,
    "failures": fail,
}
(CASE/"prepare_evidence.json").write_text(json.dumps(evidence, indent=2)+"\n")

if fail:
    print("R14_EVR1D_PREPARE: FAIL")
    for x in fail:
        print("  -", x)
    raise SystemExit(1)

print("R14_EVR1D_PREPARE: PASS")
