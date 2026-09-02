#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, os, subprocess, sys

CASE=Path(__file__).resolve().parent
QPX=Path(os.environ["QPX_ROOT"]).resolve()
QVT=CASE/"qvt.msh"
MESH_I=CASE/"mesh.i"
PHYS=CASE/"physics.i"
OUT=CASE/"input.i"
DB=CASE/"transport_data.txt"
C=QPX/"src"/"materials"/"QPXThermalDiffusionMaterial.C"
H=QPX/"include"/"materials"/"QPXThermalDiffusionMaterial.h"

EXPECTED={
 "QVT":"a98521af2c106137f9635fe7e2c5ba9b0fd408e17c62eb7c6d3f7c1fff65a03e",
 "MESH_I":"b31a8cbc41fd8eea60b6bc036b6a5841342c065152a91416063ff5afbec9137d",
 "DB":"2fa7988c79f6ea23ebdd50e6d1d7fc5018dc8854a27459511ec95c94ebe7ff3d",
 "C":"4533a3a2fe0d77f3d85ca171f9093907a76514dd024c5392c08dd8d17a2f4b7e",
 "H":"8f97db663781c5788e18bb98cca284a9173597a2b7bfe44f148ca2beef9391c5",
}

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
fail=[]

if not os.environ.get("CONDA_PREFIX"):
    fail.append("CONDA_PREFIX is empty; activate MOOSE/QPX conda environment")

for label,p in [("QVT",QVT),("MESH_I",MESH_I),("DB",DB),("C",C),("H",H)]:
    if not p.is_file():
        fail.append(f"missing {label}: {p}")
        continue
    got=sha(p)
    print(f"{label}_SHA256={got}")
    if got!=EXPECTED[label]:
        fail.append(f"{label} hash mismatch")

if not fail:
    if subprocess.run([sys.executable,str(CASE/"validate_fixed_contract.py")]).returncode!=0:
        fail.append("fixed mesh contract/mutation self-test failed")
if not fail:
    if subprocess.run([sys.executable,str(CASE/"oracle.py"),"--self-test",str(DB)]).returncode!=0:
        fail.append("independent D_mix oracle self-test failed")

if not fail:
    OUT.write_bytes(MESH_I.read_bytes()+b"\n"+PHYS.read_bytes())
    print(f"GENERATED_INPUT_SHA256={sha(OUT)}")

evidence={
 "status":"PASS" if not fail else "FAIL",
 "classification":"R18_QVT_PLASMA_TRANSPORT_PREFLIGHT",
 "qvt_sha256":sha(QVT) if QVT.is_file() else None,
 "mesh_i_sha256":sha(MESH_I) if MESH_I.is_file() else None,
 "transport_data_sha256":sha(DB) if DB.is_file() else None,
 "failures":fail,
}
(CASE/"prepare_evidence.json").write_text(json.dumps(evidence,indent=2)+"\n")

if fail:
    print("R18_QVT_PREPARE: FAIL")
    for x in fail: print("  -",x)
    raise SystemExit(1)
print("R18_QVT_PREPARE: PASS")
