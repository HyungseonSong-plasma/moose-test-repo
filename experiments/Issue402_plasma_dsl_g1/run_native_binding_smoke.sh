#!/usr/bin/env bash
# Issue #402 G1 native opt-in test. Do NOT modify production S4/S5/S6 inputs.
# Run from checkout root:
#   bash experiments/Issue402_plasma_dsl_g1/run_native_binding_smoke.sh
set -euo pipefail
test "$(git rev-parse --show-toplevel)" = "$PWD"
export PINNED_BASE="ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
export PILOT="experiments/Issue402_plasma_dsl_g1"
export EVIDENCE="$PILOT/evidence"
mkdir -p "$EVIDENCE"
test -f "$PILOT/baseline.i"
test -f "$PILOT/valid_bindings.i"

{
  printf 'source_sha=%s\n' "$(git rev-parse HEAD)"
  printf 'build_base_ref=%s\n' "$PINNED_BASE"
  sha256sum "$PILOT"/*.i physics_app/include/physics/PlasmaSpeciesContinuityPhysics.h \
    physics_app/src/physics/PlasmaSpeciesContinuityPhysics.C physics_app/src/base/PhysicsApp.C
} > "$EVIDENCE/provenance.txt"

docker pull "$PINNED_BASE"
docker run --rm --entrypoint /bin/bash --user 0:0 \
  --workdir /workspace -v "$PWD:/workspace" "$PINNED_BASE" -lc '
  set -euo pipefail
  source /environment
  git config --global --add safe.directory /workspace
  export MOOSE_DIR=/opt/physics_vendor/moose
  export CRANE_DIR=/opt/physics_vendor/crane
  export SQUIRREL_DIR=/opt/physics_vendor/squirrel
  export ZAPDOS_DIR=/opt/physics_vendor/zapdos
  export METHOD=opt
  make -C physics_app -j2
' 2>&1 | tee "$EVIDENCE/native_build.log"
test -x physics_app/physics-opt

native() {
  docker run --rm --entrypoint /bin/bash --user 0:0 \
    --workdir /workspace -v "$PWD:/workspace" "$PINNED_BASE" -lc '
    set -euo pipefail
    source /environment
    physics_app/physics-opt "$@"
  ' -- "$@"
}

native --check-input -i "$PILOT/baseline.i" \
  2>&1 | tee "$EVIDENCE/baseline_check.log"
native --check-input -i "$PILOT/baseline.i" "$PILOT/valid_bindings.i" \
  2>&1 | tee "$EVIDENCE/valid_bindings_check.log"
echo "P402_G1_NATIVE_VALID_BINDINGS_CHECK_PASS"

for item in invalid_overlap invalid_fem_fv_swap invalid_generate invalid_missing_variable; do
  set +e
  native --check-input -i "$PILOT/baseline.i" "$PILOT/$item.i" \
    > "$EVIDENCE/$item.log" 2>&1
  code=$?
  set -e
  if [[ "$code" -eq 0 ]] || ! grep -Eq 'P402_(SPECIES|OWNER)' "$EVIDENCE/$item.log"; then
    echo "::error::G1 negative input unexpectedly accepted or wrong diagnostic: $item" >&2
    cat "$EVIDENCE/$item.log" >&2
    exit 22
  fi
  printf '%s: expected rejection PASS\n' "$item"
done
echo "P402_G1_NATIVE_NEGATIVE_INPUTS_PASS"

mkdir -p "$EVIDENCE/baseline" "$EVIDENCE/candidate"
native -i "$PILOT/baseline.i" "Outputs/file_base=$EVIDENCE/baseline/plasma" \
  2>&1 | tee "$EVIDENCE/baseline_run.log"
native -i "$PILOT/baseline.i" "$PILOT/valid_bindings.i" \
  "Outputs/file_base=$EVIDENCE/candidate/plasma" \
  2>&1 | tee "$EVIDENCE/candidate_run.log"
test -s "$EVIDENCE/baseline/plasma.e"
test -s "$EVIDENCE/candidate/plasma.e"
python3 "$PILOT/compare_native_outputs.py" \
  --baseline "$EVIDENCE/baseline/plasma.e" \
  --candidate "$EVIDENCE/candidate/plasma.e" \
  --output "$EVIDENCE/numerical_parity.json"
echo "P402_G1_EXTERNAL_BINDING_NATIVE_RUN_PARITY_PASS"
