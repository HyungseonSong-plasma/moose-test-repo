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
    physics_app/include/physics/plasma/DDContinuityEq.h \
    physics_app/src/physics/plasma/DDContinuityEq.C \
    physics_app/include/physics/plasma/DDEnergyEq.h \
    physics_app/src/physics/plasma/DDEnergyEq.C \
    physics_app/src/physics/plasma/Chemistry.C \
    physics_app/include/physics/plasma/Chemistry.h \
    physics_app/src/physics/plasma/PoissonEq.C \
    physics_app/src/physics/plasma/MaxwellPhysics.C physics_app/src/base/PhysicsApp.C \
    physics_app/src/materials/DDMaterial.C \
    physics_app/include/materials/DDMaterial.h \
    physics_app/src/materials/NVMaterial.C \
    physics_app/include/materials/NVMaterial.h \
    physics_app/src/materials/PhysicsPlasmaChargeDensityMaterial.C \
    physics_app/include/materials/PhysicsPlasmaChargeDensityMaterial.h

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

# Automatic species-based DDMaterial and JSON-sourced NVMaterial.
# No transport-coefficient [FunctorMaterials] declarations in this deck.
native --check-input -i "$PILOT/valid_json_generated_transport.i" \
  2>&1 | tee "$EVIDENCE/json_generated_transport_check.log"
echo "PLASMA_JSON_TRANSPORT_GENERATION_P2_PASS"
# AD-preserving DDMaterial model=functor generated directly from JSON.
native --check-input -i "$PILOT/valid_json_generated_functor.i" \
  2>&1 | tee "$EVIDENCE/json_generated_functor_check.log"
echo "PLASMA_JSON_FUNCTOR_TRANSPORT_GENERATION_P2_PASS"
# Single-provider checks: DDMaterial creates canonical ion mu/D; the
# separate charge-density Material owns n_i and Poisson-source Functors.
# The retired charge-transport assembler is not instantiated.
native --check-input -i "$PILOT/charge_core_ddmaterial_owner_p2.i" \
  2>&1 | tee "$EVIDENCE/charge_core_ddmaterial_owner_p2.log"
echo "PLASMA_DDMATERIAL_ION_COEFFICIENT_SINGLE_OWNER_P2_PASS"
# Only Material logic may derive canonical mobility/diffusivity names.
set +e
native --check-input -i "$PILOT/invalid_json_functor_name_override_p2.i" \
  > "$EVIDENCE/invalid_json_functor_name_override_p2.log" 2>&1
bad_functor_status=$?
set -e
if [[ "$bad_functor_status" -eq 0 ]] || \
   ! grep -Fq "functor transport accepts only model" "$EVIDENCE/invalid_json_functor_name_override_p2.log"; then
  echo "::error::JSON functor source-name override was accepted or misdiagnosed" >&2
  cat "$EVIDENCE/invalid_json_functor_name_override_p2.log" >&2
  exit 28
fi
echo "PLASMA_JSON_FUNCTOR_SOURCE_OVERRIDE_REJECTED"

# One JSON entry per selected FEM/FVM species: both table modes and constants.
native --check-input -i "$PILOT/valid_json_dd_fem_fvm_mixed_p2.i" \
  2>&1 | tee "$EVIDENCE/json_dd_fem_fvm_mixed_check.log"
echo "PLASMA_JSON_DD_FEM_FVM_MIXED_P2_PASS"

for entry in "invalid_json_dd_missing_om_p2:Missing drift-diffusion transport JSON record for FVM species 'Om'" \
             "invalid_json_dd_bad_lookup_p2:DDMaterial lookup coefficients must be finite and nonnegative"; do
  item="${entry%%:*}"
  expected="${entry#*:}"
  set +e
  native --check-input -i "$PILOT/$item.i" > "$EVIDENCE/$item.log" 2>&1
  result=$?
  set -e
  if [[ "$result" -eq 0 ]] || ! grep -Fq "$expected" "$EVIDENCE/$item.log"; then
    echo "::error::JSON transport guard failed: $item" >&2
    cat "$EVIDENCE/$item.log" >&2
    exit 27
  fi
done
echo "PLASMA_JSON_DD_MISSING_AND_INVALID_LOOKUP_REJECTED"

# Density-paired species create their own FEM/FV variables and log-molar ICs.
# These are parser/P2 checks only; no P3 or physical S6 run.
native --check-input -i "$PILOT/species_density_pairs_p2.i" \
  2>&1 | tee "$EVIDENCE/species_density_pairs_p2.log"
echo "PLASMA_SPECIES_DENSITY_PAIRS_P2_PASS"
# Physics-generated energy/potential states, exact-head P2 check only.
native --check-input -i "$PILOT/auto_energy_potential_p2.i" \
  2>&1 | tee "$EVIDENCE/auto_energy_potential_p2.log"
echo "PLASMA_AUTO_ENERGY_POTENTIAL_P2_PASS"
for entry in "invalid_auto_energy_missing_initial_p2:requires an explicit positive initial molar" \
             "invalid_auto_energy_zero_initial_p2:must be finite and strictly positive" \
             "invalid_auto_poisson_nan_initial_p2:invalid syntax for double parameter"; do
  item="${entry%%:*}"
  expected="${entry#*:}"
  set +e
  native --check-input -i "$PILOT/$item.i" > "$EVIDENCE/$item.log" 2>&1
  result=$?
  set -e
  if [[ "$result" -eq 0 ]] || ! grep -Fq "$expected" "$EVIDENCE/$item.log"; then
    echo "::error::Invalid auto-created energy/Poisson initial value accepted: $item" >&2
    cat "$EVIDENCE/$item.log" >&2
    exit 26
  fi
done
echo "PLASMA_INVALID_AUTO_ENERGY_POTENTIAL_REJECTED"

for entry in "invalid_species_density_zero_p2:requires a finite, strictly positive" \
             "invalid_species_density_odd_p2:expected species_name initial_number_density pairs" \
             "invalid_species_density_nan_p2:requires a finite, strictly positive"; do
  item="${entry%%:*}"
  expected="${entry#*:}"
  set +e
  native --check-input -i "$PILOT/$item.i" > "$EVIDENCE/$item.log" 2>&1
  result=$?
  set -e
  if [[ "$result" -eq 0 ]] || ! grep -Fq "$expected" "$EVIDENCE/$item.log"; then
    echo "::error::Invalid species/density pairing accepted: $item" >&2
    cat "$EVIDENCE/$item.log" >&2
    exit 25
  fi
done
echo "PLASMA_INVALID_SPECIES_DENSITY_PAIRS_REJECTED"


# Synthetic equal-equation channels must create separate signed electron energy contributions.
native --check-input -i "$PILOT/chemistry_two_channels.i" \
  2>&1 | tee "$EVIDENCE/chemistry_two_channels.log"
echo "PLASMA_CHEMISTRY_TWO_CHANNELS_P2_PASS"
# Schema renames must fail closed; a negative energy_loss_eV must not turn
# physical electron loss into spurious heating.
for entry in "plasma_negative_energy_loss_p2:electron energy loss must be finite and nonnegative" \
             "plasma_legacy_energy_schema_p2:legacy reaction keys progress_units/electron_energy_change_eV"; do
  item="${entry%%:*}"
  expected="${entry#*:}"
  set +e
  native --check-input -i "$PILOT/$item.i" > "$EVIDENCE/$item.log" 2>&1
  result=$?
  set -e
  if [[ "$result" -eq 0 ]] || ! grep -Fq "$expected" "$EVIDENCE/$item.log"; then
    echo "::error::Reaction schema/sign guard failed: $item" >&2
    cat "$EVIDENCE/$item.log" >&2
    exit 29
  fi
done
echo "PLASMA_ENERGY_LOSS_AND_LEGACY_SCHEMA_REJECTED"

# Check S6 archival channel catalogues against synthetic-only kinetic providers.
# This is a parser/build P2 gate; original physical rate tables are not replayed.
for channel in 417 941; do
  native --check-input -i "$PILOT/chemistry_s6_${channel}_catalogue_p2.i" \
    2>&1 | tee "$EVIDENCE/chemistry_s6_${channel}_catalogue_p2.log"
  echo "PLASMA_CHEMISTRY_S6_${channel}_CATALOGUE_P2_PASS"
done

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

# DD: physical constants and absolute-lookup coefficients; NV: heavy binary
# collision, mixture and thermal transport. Input validation only; no timestep.
native --check-input -i "physics_app/ci/dd_nv_material_smoke.i" \
  2>&1 | tee "$EVIDENCE/dd_nv_materials_check.log"
echo "PLASMA_DD_NV_MATERIALS_P2_PASS"

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
    invalid_chemistry_reactions) expected='duplicate reaction ID or generated progress owner' ;;
    invalid_poisson_variable) expected='Poisson fem_potential requires an FEM solver variable' ;;
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
