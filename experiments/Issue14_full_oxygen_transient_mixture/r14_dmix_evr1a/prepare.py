#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, os, subprocess, sys

CASE=Path(__file__).resolve().parent
QPX=Path(os.environ["QPX_ROOT"]).resolve()
C=QPX/"src"/"materials"/"QPXThermalDiffusionMaterial.C"
H=QPX/"include"/"materials"/"QPXThermalDiffusionMaterial.h"
DB=CASE/"transport_data.txt"

EXP_C="4533a3a2fe0d77f3d85ca171f9093907a76514dd024c5392c08dd8d17a2f4b7e"
EXP_H="8f97db663781c5788e18bb98cca284a9173597a2b7bfe44f148ca2beef9391c5"
EXP_DB="2fa7988c79f6ea23ebdd50e6d1d7fc5018dc8854a27459511ec95c94ebe7ff3d"

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

fail=[]
for label,p,exp in [("C",C,EXP_C),("H",H,EXP_H),("DB",DB,EXP_DB)]:
    if not p.is_file():
        fail.append(f"missing {label}: {p}")
        print(f"{label}_SOURCE={p}")
        continue
    got=sha(p)
    print(f"{label}_SHA256={got}")
    if got!=exp:
        fail.append(f"{label} hash mismatch")

rc=subprocess.run([sys.executable,str(CASE/"validate_transport_data.py"),str(DB)]).returncode
if rc!=0:
    fail.append("transport data independent validator failed")

evidence={
    "status":"PASS" if not fail else "FAIL",
    "classification":"R14_7SPECIES_DATA_CANDIDATE",
    "qpx_root":str(QPX),
    "c_source":str(C),
    "h_source":str(H),
    "transport_data":str(DB),
    "transport_data_sha256":sha(DB) if DB.is_file() else None,
    "failures":fail,
}
(CASE/"prepare_evidence.json").write_text(json.dumps(evidence,indent=2)+"\n")

if fail:
    print("R14_EVR1A_PREPARE: FAIL")
    for x in fail: print("  -",x)
    raise SystemExit(1)

print("R14_EVR1A_PREPARE: PASS")
