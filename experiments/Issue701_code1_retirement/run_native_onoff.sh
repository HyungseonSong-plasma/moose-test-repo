#!/usr/bin/env bash
# Native Poisson-response ON/OFF characterization on the exact same PhysicsApp binary.
# Exploratory R2 ONLY; never treat a zero/different field result as SAFE_DELETE.
set -euo pipefail
test "$(git rev-parse --show-toplevel)" = "$PWD"
EXP=experiments/Issue701_code1_retirement
EVD=$EXP/evidence
mkdir -p "$EVD"
PINNED_BASE='ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008'
test -x physics_app/physics-opt

python3 - "$EXP/poisson_on.i" "$EXP/poisson_off.i" <<'PY'
from pathlib import Path
import re, sys
on,off=(Path(p).read_text() for p in sys.argv[1:3])
match=re.search(r'(?ms)^  \[electron_response_banded_correction\]\n.*?^  \[\]\n',on)
if match is None or on[:match.start()]+on[match.end():] != off:
    raise SystemExit("ON_OFF_INPUT_NOT_IDENTICAL_OUTSIDE_KERNEL_BLOCK")
matrix_match=re.search(r"(?m)^\s*matrix = '([^']+)'",match.group(0))
matrix=[float(v) for v in matrix_match.group(1).split()]
if len(matrix)!=16 or max(abs(sum(matrix[i*4+j] for j in range(4))) for i in range(4))>1e-12:
    raise SystemExit("INVALID_RESPONSE_MATRIX")
print("ON_OFF_P0=PASS_ONLY_ONE_KERNEL_BLOCK_DIFFERS")
PY

native() {
  docker run --rm --entrypoint /bin/bash --user 0:0 \
    --workdir /workspace -v "$PWD:/workspace" "$PINNED_BASE" -lc '
      set -euo pipefail
      source /environment
      physics_app/physics-opt "$@"
    ' -- "$@"
}

set +e
native --check-input -i "$EXP/poisson_on.i" > "$EVD/poisson_on_p2.log" 2>&1
on_p2=$?
native --check-input -i "$EXP/poisson_off.i" > "$EVD/poisson_off_p2.log" 2>&1
off_p2=$?
on_p3=99
off_p3=99
if [ "$on_p2" -eq 0 ] && [ "$off_p2" -eq 0 ]; then
  native -i "$EXP/poisson_on.i" > "$EVD/poisson_on_p3.log" 2>&1
  on_p3=$?
  native -i "$EXP/poisson_off.i" > "$EVD/poisson_off_p3.log" 2>&1
  off_p3=$?
fi
set -e

python3 - "$EVD" "$on_p2" "$off_p2" "$on_p3" "$off_p3" "$PINNED_BASE" <<'PY'
from pathlib import Path
import csv
import hashlib
import json
import subprocess
import sys
evidence=Path(sys.argv[1]); p2=[int(v) for v in sys.argv[2:4]]; p3=[int(v) for v in sys.argv[4:6]]
def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
head=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
case_files={}
for arm in ["on","off"]:
    case_files[arm]={
      "input_sha256":digest(f"experiments/Issue701_code1_retirement/poisson_{arm}.i"),
      "p2_log_sha256":digest(evidence/f"poisson_{arm}_p2.log"),
      "p3_log_sha256":digest(evidence/f"poisson_{arm}_p3.log") if (evidence/f"poisson_{arm}_p3.log").exists() else None,
    }
receipt={
  "schema":"fdeg.code1.native_on_off_exploratory.v0.1",
  "repository_head":head,
  "source_binary_sha256":digest("physics_app/physics-opt"),
  "oci_image":sys.argv[6],
  "inputs_differ_only_by_kernel_block":True,
  "on":dict(case_files["on"], p2_rc=p2[0],p3_rc=p3[0]),
  "off":dict(case_files["off"],p2_rc=p2[1],p3_rc=p3[1]),
  "runtime_observation":"BOTH_EXECUTED" if p3==[0,0] else "INCOMPLETE_OR_FAILED",
  "field_parity":"NOT_EVALUATED",
  "residual_jacobian_parity":"NOT_EVALUATED",
  "source_417_941_coverage":"NOT_EVALUATED",
  "safe_delete":"HOLD",
  "science_acceptance":"NOT_GRANTED"
}
(evidence/"code1_native_onoff_receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
print(json.dumps(receipt,indent=2,sort_keys=True))
PY
# Nonblocking characterization: the receipt is the output, never a parity PASS.
echo 'CODE1_ON_OFF_CHARACTERIZATION=RECORDED_HOLD'
