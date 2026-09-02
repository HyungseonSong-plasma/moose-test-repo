#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, os, sys

CASE = Path(__file__).resolve().parent
QPX = Path(os.environ["QPX_ROOT"]).resolve()

C = QPX/"src"/"materials"/"QPXThermalDiffusionMaterial.C"
H = QPX/"include"/"materials"/"QPXThermalDiffusionMaterial.h"
DB = CASE/"transport_data.txt"
INPUT = CASE/"input.i"

EXPECTED_C = "4533a3a2fe0d77f3d85ca171f9093907a76514dd024c5392c08dd8d17a2f4b7e"
EXPECTED_H = "8f97db663781c5788e18bb98cca284a9173597a2b7bfe44f148ca2beef9391c5"
EXPECTED_DB = "2fa7988c79f6ea23ebdd50e6d1d7fc5018dc8854a27459511ec95c94ebe7ff3d"

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

fail = []

for label,p,exp in [
    ("C",C,EXPECTED_C),
    ("H",H,EXPECTED_H),
    ("DB",DB,EXPECTED_DB),
]:
    if not p.is_file():
        fail.append(f"missing {label}: {p}")
        continue
    got = sha(p)
    print(f"{label}_SHA256={got}")
    if got != exp:
        fail.append(f"{label} hash mismatch")

kernel_candidates = []
for p in QPX.rglob("QPXFVThermalDiffusion.C"):
    # Never accept a temp/test copy as the production source.
    if "temp" in p.relative_to(QPX).parts:
        continue
    kernel_candidates.append(p.resolve())

if len(kernel_candidates) != 1:
    fail.append(
        f"expected exactly one production QPXFVThermalDiffusion.C; found {len(kernel_candidates)}: "
        + ", ".join(map(str,kernel_candidates))
    )
    kernel = None
else:
    kernel = kernel_candidates[0]
    source = kernel.read_text(errors="replace")
    print(f"THERMAL_KERNEL_SOURCE={kernel}")
    print(f"THERMAL_KERNEL_SHA256={sha(kernel)}")
    required = [
        'registerMooseObject("qpxApp", QPXFVThermalDiffusion)',
        'include_thermal_diffusion',
        '_temperature.gradient',
        '_thermal_diffusion_coefficient',
        'return -DT_face * dTdn / T_face;',
    ]
    for token in required:
        if token not in source:
            fail.append(f"thermal-kernel source contract missing token: {token}")

inp = INPUT.read_text()
required_input = [
    "include_thermal_diffusion = true",
    "include_thermal_diffusion = false",
    "500.0 + 200.0*x + 100.0*x^2",
    "type = QPXFVThermalDiffusion",
    "thermal_diffusion_coefficient = DT_grad_O",
]
for token in required_input:
    if token not in inp:
        fail.append(f"input localization contract missing token: {token}")

evidence = {
    "status": "PASS" if not fail else "FAIL",
    "classification": "R14_EVR1C_THERMAL_FLUX_PREFLIGHT",
    "material_c_sha256": sha(C) if C.is_file() else None,
    "material_h_sha256": sha(H) if H.is_file() else None,
    "transport_data_sha256": sha(DB) if DB.is_file() else None,
    "thermal_kernel_source": str(kernel) if kernel else None,
    "thermal_kernel_sha256": sha(kernel) if kernel else None,
    "failures": fail,
}
(CASE/"prepare_evidence.json").write_text(json.dumps(evidence,indent=2)+"\n")

if fail:
    print("R14_EVR1C_PREPARE: FAIL")
    for x in fail:
        print("  -",x)
    raise SystemExit(1)

print("R14_EVR1C_PREPARE: PASS")
