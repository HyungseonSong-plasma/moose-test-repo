#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, os, subprocess, sys

CASE = Path(__file__).resolve().parent
QPX = Path(os.environ["QPX_ROOT"]).resolve()
C = QPX/"src"/"materials"/"QPXThermalDiffusionMaterial.C"
H = QPX/"include"/"materials"/"QPXThermalDiffusionMaterial.h"
DB = CASE/"transport_data.txt"

EXPECTED = {
    "C": "4533a3a2fe0d77f3d85ca171f9093907a76514dd024c5392c08dd8d17a2f4b7e",
    "H": "8f97db663781c5788e18bb98cca284a9173597a2b7bfe44f148ca2beef9391c5",
    "DB": "2fa7988c79f6ea23ebdd50e6d1d7fc5018dc8854a27459511ec95c94ebe7ff3d",
}

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

fail = []
for label,p in [("C",C),("H",H),("DB",DB)]:
    if not p.is_file():
        fail.append(f"missing {label}: {p}")
        continue
    got = sha(p)
    print(f"{label}_SHA256={got}")
    if got != EXPECTED[label]:
        fail.append(f"{label} hash mismatch")

if not fail:
    rc = subprocess.run(
        [sys.executable, str(CASE/"oracle.py"), "--self-test", str(DB)]
    ).returncode
    if rc != 0:
        fail.append("independent oracle self-test failed")

evidence = {
    "status": "PASS" if not fail else "FAIL",
    "classification": "R14_EVR1B_ORACLE_PREFLIGHT",
    "transport_data_sha256": sha(DB) if DB.is_file() else None,
    "failures": fail,
}
(CASE/"prepare_evidence.json").write_text(json.dumps(evidence, indent=2)+"\n")

if fail:
    print("R14_EVR1B_PREPARE: FAIL")
    for x in fail:
        print("  -", x)
    raise SystemExit(1)

print("R14_EVR1B_PREPARE: PASS")
