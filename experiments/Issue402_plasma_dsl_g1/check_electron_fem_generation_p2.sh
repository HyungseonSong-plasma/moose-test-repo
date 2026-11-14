#!/usr/bin/env bash
# Issue402 electron-only P2: JSON + MOOSE input constructs two FEM equations.
# No original S6 full-stack replay or timestep. No private rate bytes.
set -euo pipefail
test "$(git rev-parse --show-toplevel)" = "$PWD"
PILOT=experiments/Issue402_plasma_dsl_g1
EVIDENCE="$PILOT/evidence"
BASE='ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008'
test "$(git rev-parse HEAD)" = "${EXPECTED_SOURCE_HEAD:-$(git rev-parse HEAD)}"
test -x physics_app/physics-opt
test -f "$EVIDENCE/electron_fem_p1_identity.json"
python3 - <<'PY'
import hashlib, json, pathlib, subprocess
e = json.loads(pathlib.Path("experiments/Issue402_plasma_dsl_g1/evidence/electron_fem_p1_identity.json").read_text())
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
assert e["source_sha"] == head
assert hashlib.sha256(pathlib.Path("physics_app/physics-opt").read_bytes()).hexdigest() == e["binary_sha256"]
assert e["P1"] == "PASS" and e["science"] == "SCIENCE_HOLD"
PY
docker run --rm --network none --entrypoint /bin/bash --user 0:0 \
  --workdir /workspace -v "$PWD:/workspace" "$BASE" -lc '
  set -euo pipefail
  source /environment
  # The bind mount is owned by the host runner, but this container runs root.
  git config --global --add safe.directory /workspace
  python3 physics_app/ci/check_issue402_electron_fem_generation_p2.py \
    /workspace/physics_app/physics-opt \
    /workspace/experiments/Issue402_plasma_dsl_g1/evidence/electron_fem_p2_receipt.json
' 2>&1 | tee "$EVIDENCE/electron_fem_p2.log"
test -s "$EVIDENCE/electron_fem_p2_receipt.json"
echo ISSUE402_ELECTRON_FEM_TWO_EQUATIONS_P2_PASS_P3_NOT_RUN_SCIENCE_HOLD
