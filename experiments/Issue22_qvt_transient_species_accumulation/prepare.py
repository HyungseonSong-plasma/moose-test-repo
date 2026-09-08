#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, os, re, sys

HERE=Path(__file__).resolve().parent
QPX_ROOT=Path(os.environ.get("QPX_ROOT", str(HERE.parents[4]))).resolve()
exp=json.loads((HERE/"expected.json").read_text())

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
fail=[]

for fn,key in [
    ("qvt.msh","qvt_sha256"),
    ("mesh.i","mesh_i_sha256"),
    ("transport_data.txt","transport_data_sha256"),
]:
    p=HERE/fn
    if not p.is_file(): fail.append("missing "+fn)
    elif sha(p)!=exp[key]: fail.append(fn+" SHA mismatch")

# Exact input rebuild.
if (HERE/"mesh.i").is_file() and (HERE/"physics.i").is_file():
    (HERE/"input.i").write_bytes((HERE/"mesh.i").read_bytes()+b"\n"+(HERE/"physics.i").read_bytes())
if not (HERE/"input.i").is_file() or sha(HERE/"input.i")!=exp["input_sha256"]:
    fail.append("rebuilt input.i SHA mismatch")

# Production source identity from accepted EVR1 source.
for rel,want in exp["production_source_sha256"].items():
    p=QPX_ROOT/rel
    if not p.is_file():
        fail.append("missing production source "+str(p))
    elif sha(p)!=want:
        fail.append("production source SHA mismatch "+rel)

t=(HERE/"physics.i").read_text()

required=[
 "type = QPXFVConservativeMassFractionTimeDerivative",
 "type = WCNSFVMassTimeDerivative",
 "drho_dt = drho_dt_model",
 "type = QPXFVMassFractionAdvection",
 "type = QPXFVMixtureAveragedDiffusion",
 "scheme = implicit-euler",
 "property_name = dMn_dt_model",
 "property_name = drho_dt_model",
 "define_dot_functors = true",
 "type = ADElementIntegralFunctorPostprocessor",
 "execute_on = 'INITIAL TIMESTEP_END'",
]
for tok in required:
    if tok not in t: fail.append("missing contract token: "+tok)

if t.count("type = QPXFVConservativeMassFractionTimeDerivative") != 6:
    fail.append("expected exactly 6 conservative species time kernels")
if t.count("type = QPXFVMassFractionAdvection") != 6:
    fail.append("expected exactly 6 species advection kernels")
if t.count("type = QPXFVMixtureAveragedDiffusion") != 6:
    fail.append("expected exactly 6 mixture diffusion kernels")
if "type = QPXFVMassFractionTimeDerivative" in t:
    fail.append("legacy rho*dw/dt species kernel must not appear in EVR2 production candidate")

# Parser namespace gate.
reserved={"x","y","z","t","pi","e"}
for raw in re.findall(r"functor_symbols\s*=\s*'([^']+)'",t):
    aliases=raw.split()
    bad=reserved.intersection(aliases)
    if bad: fail.append("reserved parser symbol collision: "+",".join(sorted(bad)))

# Exact oxygen molar-mass derivative algebra used in the chain-rule flow continuity.
if "expression = '-31.25*mnv*mnv*(dwo+dwom+dwop+dwos)'" not in t:
    fail.append("dMn/dt oxygen-family identity missing")
if "expression = '(mnv*dpv+prv*dmnv)/(8.31446*tgv)'" not in t:
    fail.append("drho/dt EOS chain identity missing")

# Temporal schema must route the checker to physical-only CSV.
cfg=json.loads((HERE/"test.json").read_text())
if cfg.get("validation_schema") != 2:
    fail.append("validation_schema=2 required")
specs=cfg.get("temporal_csv",[])
if len(specs)!=1 or specs[0].get("initial_row_policy")!="exclude_observation":
    fail.append("runner-owned initialization-row exclusion missing")
if "input_out.physical.csv" not in [str(x) for x in cfg.get("checker_args",[])]:
    fail.append("checker must consume input_out.physical.csv")
if "input_out.csv" in [str(x) for x in cfg.get("checker_args",[])]:
    fail.append("checker must not consume raw transient CSV")

# Source executable should have been rebuilt after EVR1 source installation.
exe=Path(os.environ.get("QPX_EXECUTABLE",QPX_ROOT/"qpx-opt")).resolve()
if exe.is_file():
    src_times=[]
    for rel in exp["production_source_sha256"]:
        p=QPX_ROOT/rel
        if p.is_file(): src_times.append(p.stat().st_mtime)
    if src_times and exe.stat().st_mtime < max(src_times):
        fail.append("SOURCE_REBUILD_REQUIRED: qpx-opt older than #22 production source")

print("R22_EVR2_PARSER_NAMESPACE_P0:",
      "PASS" if not any("parser symbol" in x for x in fail) else "FAIL")
print("R22_EVR2_TEMPORAL_SCHEMA_P0:",
      "PASS" if not any("CSV" in x or "validation_schema" in x or "initialization-row" in x for x in fail) else "FAIL")
print("R22_EVR2_STRUCTURAL_P0:", "PASS" if not fail else "FAIL")
if fail:
    for x in fail: print("  -",x)
    raise SystemExit(2)
