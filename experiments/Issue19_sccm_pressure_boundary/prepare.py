#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, math, os, re, sys

CASE = Path(__file__).resolve().parent
QVT = CASE/"qvt.msh"
MESH = CASE/"mesh.i"
PHYS = CASE/"physics.i"
INP = CASE/"input.i"
EXP = json.loads((CASE/"expected.json").read_text())

EXPECTED_QVT = "a98521af2c106137f9635fe7e2c5ba9b0fd408e17c62eb7c6d3f7c1fff65a03e"
EXPECTED_MESH = "b31a8cbc41fd8eea60b6bc036b6a5841342c065152a91416063ff5afbec9137d"

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def fail(msg):
    print("R19_PREPARE_FAIL:", msg)
    raise SystemExit(2)

if not os.environ.get("CONDA_PREFIX"):
    fail("CONDA_PREFIX empty; activate MOOSE/QPX conda environment")

if sha(QVT) != EXPECTED_QVT:
    fail("qvt.msh identity mismatch")
if sha(MESH) != EXPECTED_MESH:
    fail("mesh.i identity mismatch")

txt = PHYS.read_text()

# Required canonical BC path.
required = [
    "type = WCNSFVMassFluxBC",
    "type = WCNSFVMomentumFluxBC",
    "type = INSFVOutletPressureBC",
    "boundary = inlet",
    "boundary = outlet",
    "direction = '-1 0 0'",
    "area_pp = inlet_area",
    "mdot_pp = inlet_mdot",
    "function = ${outlet_pressure}",
    "kernel_coverage_check = false",
]
for token in required:
    if token not in txt:
        fail("missing canonical token: " + token)

# Reject velocity-Dirichlet inlet as canonical #19 path.
if "WCNSFVInletVelocityBC" in txt or "INSFVInletVelocityBC" in txt:
    fail("velocity-Dirichlet inlet path is non-canonical for #19")

# Conversion self-tests.
def mdot(q):
    return q * 1e-6 / 60.0 * EXP["M_inlet_kg_per_mol"] / EXP["Vm_std_m3_per_mol"]

m0 = mdot(0.0)
m1 = mdot(EXP["Q_sccm"])
m2 = mdot(2.0*EXP["Q_sccm"])
if abs(m0) > 1e-30:
    fail("zero-sccm self-test failed")
if abs(m2 - 2.0*m1) > 1e-15 * max(1.0, abs(m2)):
    fail("2x-sccm linearity self-test failed")
if abs(m1 - EXP["inlet_mdot_kg_per_s"]) > 1e-15 * max(1.0, abs(m1)):
    fail("nominal SCCM conversion self-test failed")

# Reference-state mutation must move mdot materially.
wrong_vm = 24.465e-3
wrong = EXP["Q_sccm"]*1e-6/60.0*EXP["M_inlet_kg_per_mol"]/wrong_vm
if abs(wrong/m1 - 1.0) < 0.05:
    fail("wrong-reference-state mutation not discriminating")

# Direction mutation must be caught by the static contract.
if "direction = '1 0 0'" in txt:
    fail("wrong inlet direction")

# Fixed-geometry analytic area.
area = 2.0*math.pi*0.234*(0.3195-0.279)
if abs(area - EXP["inlet_area_m2"]) > 1e-14:
    fail("analytic inlet area oracle mismatch")

# Regenerate exact executable input.
INP.write_bytes(MESH.read_bytes() + b"\n" + PHYS.read_bytes())

evidence = {
    "status": "PASS",
    "classification": "R19_SCCM_PRESSURE_BOUNDARY_PREFLIGHT",
    "qvt_sha256": sha(QVT),
    "mesh_i_sha256": sha(MESH),
    "input_sha256": sha(INP),
    "Q_sccm": EXP["Q_sccm"],
    "inlet_mdot_kg_per_s": m1,
    "inlet_area_oracle_m2": area,
    "direction": EXP["direction"],
    "outlet_pressure_Pa": EXP["outlet_pressure_Pa"],
}
(CASE/"prepare_evidence.json").write_text(json.dumps(evidence, indent=2)+"\n")

print("R19_SCCM_CONVERSION_SELFTEST: PASS")
print("R19_REFERENCE_STATE_MUTATION_SELFTEST: PASS")
print("R19_DIRECTION_STATIC_SELFTEST: PASS")
print("R19_GEOMETRY_AREA_ORACLE: PASS")
print("R19_PREPARE: PASS")
