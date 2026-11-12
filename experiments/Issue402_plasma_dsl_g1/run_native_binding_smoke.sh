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

# Python-only contracts; build the existing MOOSE application, never generate source code.
python3 physics_app/ci/check_plasma_closures_contract.py
test -f physics_app/ci/plasma_direct_existing_materials_smoke.i

{
  printf 'source_sha=%s\n' "$(git rev-parse HEAD)"
  printf 'build_base_ref=%s\n' "$PINNED_BASE"
  sha256sum "$PILOT"/*.i "$PILOT"/*.json physics_app/include/physics/plasma/PlasmaInterface.h \
    physics_app/src/physics/plasma/PlasmaInterface.C \
    physics_app/include/physics/plasma/ContinuityEq.h \
    physics_app/src/physics/plasma/ContinuityEq.C \
    physics_app/src/physics/plasma/EnergyPhysics.C \
    physics_app/src/physics/plasma/ChemistryPhysics.C \
    physics_app/src/physics/plasma/PoissonPhysics.C \
    physics_app/src/physics/plasma/MaxwellPhysics.C physics_app/src/base/PhysicsApp.C \
    physics_app/src/materials/ElectronClosureMaterial.C \
    physics_app/src/materials/ElectronTransportLookupMaterial.C \
    physics_app/src/materials/PlasmaChargeTransportMaterial.C \
    physics_app/include/materials/SpeciesTransportAliasMaterial.h \
    physics_app/src/materials/SpeciesTransportAliasMaterial.C
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
# Reuse this exact build across all small and full-S6 P2 cases in this job.
# This is NOT a cross-job cache or scientific equivalence certificate.
python3 - "$EVIDENCE/native_p1_identity.json" "$(git rev-parse HEAD)" "$PINNED_BASE" \
  "physics_app/physics-opt" "$EVIDENCE/native_build.log" <<'PY'
import hashlib
import json
import pathlib
import sys
def digest(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()
target = pathlib.Path(sys.argv[1])
if target.exists():
    raise RuntimeError("Refusing to overwrite P1 identity evidence")
target.write_text(json.dumps({
    "schema": "issue402.native_p1.job_local.v1",
    "source_sha": sys.argv[2],
    "oci_image": sys.argv[3],
    "binary_sha256": digest(sys.argv[4]),
    "build_log_sha256": digest(sys.argv[5]),
    "reusable_scope": "same_exact_head_ci_job_only",
    "P1": "PASS",
    "P3": "NOT_RUN",
    "science": "SCIENCE_HOLD",
}, indent=2, sort_keys=True) + "\n")
PY

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
# Verify canonical names e/O2p/Om/Op from a standalone, untouched P2 fixture.
native --check-input -i "$PILOT/generic_four_species.i" \
  2>&1 | tee "$EVIDENCE/generic_four_species_check.log"
echo "PLASMA_GENERIC_SPECIES_STATE_NAMES_P2_PASS"
native --check-input -i "$PILOT/baseline.i" "$PILOT/valid_all_physics.i" \
  2>&1 | tee "$EVIDENCE/all_physics_check.log"
# Standalone positive construction check: one generated FEM transport Kernel.
# It is a P2-only input, not an accepted physical simulation or P3 parity run.
native --check-input -i "$PILOT/baseline.i" "$PILOT/valid_generated_transport_options.i" \
  2>&1 | tee "$EVIDENCE/valid_generated_transport_options.log"
echo "PLASMA_OPTION_ONLY_FEM_GENERATION_P2_PASS"

# Synthetic equal-equation channels must create separate signed electron energy contributions.
native --check-input -i "$PILOT/chemistry_two_channels.i" \
  2>&1 | tee "$EVIDENCE/chemistry_two_channels.log"
echo "PLASMA_CHEMISTRY_TWO_CHANNELS_P2_PASS"

# Negative P2: no second Native time derivative alongside generated e_time.
# This checks semantic Kernel type + variable ownership, not object name only.
set +e
native --check-input -i "$PILOT/baseline.i" \
  "$PILOT/valid_generated_transport_options.i" \
  "$PILOT/duplicate_e_time.i" > "$EVIDENCE/duplicate_e_time.log" 2>&1
duplicate_time_exit=$?
set -e
if [[ "$duplicate_time_exit" -eq 0 ]] ||
   ! grep -Fq "FEMLogMolarTimeDerivative" "$EVIDENCE/duplicate_e_time.log" ||
   ! grep -Fq "must have exactly one owner" "$EVIDENCE/duplicate_e_time.log"; then
  echo "::error::A Native and Physics-generated electron time operator were both accepted" >&2
  cat "$EVIDENCE/duplicate_e_time.log" >&2
  exit 24
fi
echo "PLASMA_DUPLICATE_E_TIME_REJECTED"
echo "PLASMA_VARIABLE_CHECK_PASSED"

# Native P2 exercises existing registered Materials via checked-in input, not a C++ generator.
native --check-input -i "physics_app/ci/plasma_direct_existing_materials_smoke.i" \
  2>&1 | tee "$EVIDENCE/direct_materials_check.log"
echo "PLASMA_DIRECT_EXISTING_MATERIALS_P2_PASS"

for item in invalid_overlap invalid_fem_fv_swap invalid_no_species invalid_missing_variable invalid_energy_species invalid_chemistry_reactions invalid_poisson_variable invalid_maxwell_frequency invalid_legacy_variables invalid_legacy_kernel_names invalid_missing_fvm_charges invalid_incomplete_coefficients invalid_wrong_charge_sign; do
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
    invalid_chemistry_reactions) expected='duplicate/empty reaction ID or progress owner' ;;
    invalid_poisson_variable) expected='Electric potential variable was not found' ;;
    invalid_maxwell_frequency) expected='The frequency must be greater than zero' ;;
    invalid_missing_variable) expected='was not found' ;;
    invalid_legacy_variables) expected='variables' ;;
    invalid_legacy_kernel_names) expected='fem_kernel_names' ;;
    invalid_missing_fvm_charges) expected='fem_charge_numbers' ;;
    invalid_incomplete_coefficients) expected='mobility' ;;
    invalid_wrong_charge_sign) expected='fem_charge_numbers' ;;
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

set +e
native --check-input -i "$PILOT/rf_explicit.i" "$PILOT/duplicate_maxwell.i" \
  > "$EVIDENCE/duplicate_maxwell.log" 2>&1
duplicate_exit=$?
set -e
if [[ "$duplicate_exit" -eq 0 ]] ||
    ! grep -Fq "must have exactly one owner" "$EVIDENCE/duplicate_maxwell.log"; then
  echo "::error::A native and Physics-generated Maxwell operator were both accepted" >&2
  cat "$EVIDENCE/duplicate_maxwell.log" >&2
  exit 23
fi
echo "PLASMA_DUPLICATE_NATIVE_KERNEL_REJECTED"

native --check-input -i "$PILOT/rf_generated.i" 2>&1 | tee "$EVIDENCE/rf_generated_check.log"
native --check-input -i "$PILOT/rf_explicit.i" 2>&1 | tee "$EVIDENCE/rf_explicit_check.log"
mkdir -p "$EVIDENCE/rf_generated" "$EVIDENCE/rf_explicit"
native -i "$PILOT/rf_generated.i" "Outputs/file_base=$EVIDENCE/rf_generated/rf" \
  2>&1 | tee "$EVIDENCE/rf_generated_run.log"
native -i "$PILOT/rf_explicit.i" "Outputs/file_base=$EVIDENCE/rf_explicit/rf" \
  2>&1 | tee "$EVIDENCE/rf_explicit_run.log"
test -s "$EVIDENCE/rf_generated/rf.e"
test -s "$EVIDENCE/rf_explicit/rf.e"
python3 "$PILOT/compare_native_outputs.py" \
  --baseline "$EVIDENCE/rf_explicit/rf.e" \
  --candidate "$EVIDENCE/rf_generated/rf.e" \
  --output "$EVIDENCE/rf_builder_parity.json"
echo "PLASMA_MAXWELL_OBJECT_GENERATION_MATCHES_NATIVE_INPUT"
