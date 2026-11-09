#!/usr/bin/env bash
# Check species variables without changing simulation equations.
# Do not change existing production simulation inputs.
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
  sha256sum "$PILOT"/*.i physics_app/include/physics/plasma/PlasmaInterface.h \
    physics_app/src/physics/plasma/PlasmaInterface.C \
    physics_app/include/physics/plasma/ContinuityPhysics.h \
    physics_app/src/physics/plasma/ContinuityPhysics.C \
    physics_app/src/physics/plasma/EnergyPhysics.C \
    physics_app/src/physics/plasma/ChemistryPhysics.C \
    physics_app/src/physics/plasma/PoissonPhysics.C \
    physics_app/src/physics/plasma/MaxwellPhysics.C physics_app/src/base/PhysicsApp.C
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
  make -C physics_app -j2 app_non_unity_dirs='%/utils'
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
native --check-input -i "$PILOT/baseline.i" "$PILOT/valid_all_physics.i" \
  2>&1 | tee "$EVIDENCE/all_physics_check.log"
echo "PLASMA_VARIABLE_CHECK_PASSED"

for item in invalid_overlap invalid_fem_fv_swap invalid_no_species invalid_missing_variable invalid_energy_species invalid_chemistry_reactions invalid_poisson_variable invalid_maxwell_frequency; do
  set +e
  native --check-input -i "$PILOT/baseline.i" "$PILOT/$item.i" \
    > "$EVIDENCE/$item.log" 2>&1
  code=$?
  set -e
  case "$item" in
    invalid_overlap) expected='species listed in both groups' ;;
    invalid_fem_fv_swap) expected='wrong type' ;;
    invalid_no_species) expected='List at least one species' ;;
    invalid_energy_species) expected="Electron energy requires fem_species" ;;
    invalid_chemistry_reactions) expected='Repeated or empty reaction name' ;;
    invalid_poisson_variable) expected='Electric potential variable was not found' ;;
    invalid_maxwell_frequency) expected='The frequency must be greater than zero' ;;
    invalid_missing_variable) expected='was not found' ;;
  esac
  if [[ "$code" -eq 0 ]] || ! grep -Fq "$expected" "$EVIDENCE/$item.log"; then
    echo "::error::Invalid input was accepted or reported the wrong error: $item" >&2
    cat "$EVIDENCE/$item.log" >&2
    exit 22
  fi
  printf '%s: expected rejection PASS\n' "$item"
done
echo "PLASMA_INVALID_INPUTS_REJECTED"

mkdir -p "$EVIDENCE/baseline" "$EVIDENCE/candidate"
native -i "$PILOT/baseline.i" "Outputs/file_base=$EVIDENCE/baseline/plasma" \
  2>&1 | tee "$EVIDENCE/baseline_run.log"
native -i "$PILOT/baseline.i" "$PILOT/valid_all_physics.i" \
  "Outputs/file_base=$EVIDENCE/candidate/plasma" \
  2>&1 | tee "$EVIDENCE/candidate_run.log"
test -s "$EVIDENCE/baseline/plasma.e"
test -s "$EVIDENCE/candidate/plasma.e"
python3 "$PILOT/compare_native_outputs.py" \
  --baseline "$EVIDENCE/baseline/plasma.e" \
  --candidate "$EVIDENCE/candidate/plasma.e" \
  --output "$EVIDENCE/numerical_parity.json"
echo "PLASMA_RESULTS_MATCH"
