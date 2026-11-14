#!/usr/bin/env bash
# Issue402 electron-FEM-only P1: compile the exact PR-head PhysicsApp.
# This does not execute the old diffusion/Poisson/RF/native legacy suite.
set -euo pipefail
test "$(git rev-parse --show-toplevel)" = "$PWD"
PILOT=experiments/Issue402_plasma_dsl_g1
EVIDENCE="$PILOT/evidence"
BASE='ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008'
mkdir -p "$EVIDENCE"
test "$(git rev-parse HEAD)" = "${EXPECTED_SOURCE_HEAD:-$(git rev-parse HEAD)}"
grep -Fq 'sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008' physics_app/dependencies.lock
python3 -m py_compile physics_app/ci/check_issue402_dd_json_plasma_boundary_p2.py
docker pull "$BASE"
docker run --rm --entrypoint /bin/bash --user 0:0 \
  --workdir /workspace -v "$PWD:/workspace" "$BASE" -lc '
  set -euo pipefail
  source /environment
  git config --global --add safe.directory /workspace
  export MOOSE_DIR=/opt/physics_vendor/moose
  export CRANE_DIR=/opt/physics_vendor/crane
  export SQUIRREL_DIR=/opt/physics_vendor/squirrel
  export ZAPDOS_DIR=/opt/physics_vendor/zapdos
  export METHOD=opt
  make -C physics_app -j2 app_non_unity_dirs="%/utils"
' 2>&1 | tee "$EVIDENCE/electron_fem_build.log"
test -x physics_app/physics-opt
python3 - "$EVIDENCE/electron_fem_p1_identity.json" "$BASE" <<'PY'
import hashlib
import json
import pathlib
import subprocess
import sys
path = pathlib.Path(sys.argv[1])
assert not path.exists(), "Refusing to overwrite P1 provenance"
binary = pathlib.Path("physics_app/physics-opt")
build_log = pathlib.Path("experiments/Issue402_plasma_dsl_g1/evidence/electron_fem_build.log")
path.write_text(json.dumps({
    "schema": "issue402.electron_fem_generation.native_p1.v1",
    "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "build_base": sys.argv[2],
    "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    "build_log_sha256": hashlib.sha256(build_log.read_bytes()).hexdigest(),
    "P1": "PASS",
    "P2": "NOT_RUN",
    "P3": "NOT_RUN",
    "P4": "NOT_RUN",
    "science": "SCIENCE_HOLD",
}, indent=2, sort_keys=True) + "\n")
PY
echo ISSUE402_ELECTRON_FEM_GENERATION_NATIVE_P1_PASS
