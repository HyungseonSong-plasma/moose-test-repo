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
    physics_app/src/materials/DDTransportMaterial.C \
    physics_app/include/materials/DDTransportMaterial.h \
    physics_app/src/materials/NVTransportMaterial.C \
    physics_app/include/materials/NVTransportMaterial.h \
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

# Issue #633: narrow positive P2 before broad legacy/surface/Poisson checks.
# This is synthetic three-ion FV Continuity only: JSON owns initial densities,
# transport and reaction sources; no Native ion Kernels/BCs, wall or Poisson.
# Reuse this job's freshly compiled exact-HEAD physics-opt, never a cached binary.
native --check-input -i "$PILOT/issue633_ion_continuity_newonly_p2.i" \
  2>&1 | tee "$EVIDENCE/issue633_ion_continuity_newonly_p2.log"
echo "ISSUE633_ION_CONTINUITY_NEW_ONLY_P2_PASS"

# C2 combined P2: synthetic 2D sidesets with actual 3 species x 4 FV kernels,
# 3 new wall-flux Materials, 12 JSON-generated FV BCs, and three surface
# current functors. No Native ion operators and no Poisson or time integration.
# Never treat synthetic P2 as full S6-417/941 replacement/science acceptance.
native --check-input -i "$PILOT/issue633_ion_continuity_wall_bc_newonly_p2.i" \
  2>&1 | tee "$EVIDENCE/issue633_ion_continuity_wall_bc_newonly_p2.log"
echo "ISSUE633_ION_CONTINUITY_WALL_BC_NEW_ONLY_P2_PASS"

# Exact-HEAD negative P2: Om lacks a volume source, so the otherwise valid
# JSON + .i selection must fail before accepting a partial FV equation.
set +e
native --check-input -i "$PILOT/issue633_ion_continuity_missing_om_source_p2.i" \
  > "$EVIDENCE/issue633_ion_continuity_missing_om_source_p2.log" 2>&1
issue633_missing_om_status=$?
set -e
if [[ "$issue633_missing_om_status" -eq 0 ]] || \
   ! grep -Fq "requires a nonzero volume reaction source" \
       "$EVIDENCE/issue633_ion_continuity_missing_om_source_p2.log"; then
  echo "::error::Issue633 omitted Om source was accepted or failed for the wrong reason" >&2
  cat "$EVIDENCE/issue633_ion_continuity_missing_om_source_p2.log" >&2
  exit 41
fi
echo "ISSUE633_ION_CONTINUITY_MISSING_SOURCE_NEGATIVE_P2_PASS"

# Canonical replacement for the historical JSON-rate one-shot Native P2 cases.
# Use the exact same physics-opt binary and immutable OCI as P1 and later S6 P2.
# H01-H04, H05 and the actual JSON surface-rate input do not execute timesteps.
docker run --rm --entrypoint /bin/bash --user 0:0 \
  --workdir /workspace -v "$PWD:/workspace" \
  -e "EXPECTED_HEAD=$(git rev-parse HEAD)" \
  -e "PINNED_BASE=$PINNED_BASE" "$PINNED_BASE" -lc '
  set -euo pipefail
  source /environment
  python3 -m physics_app.ci.check_issue402_json_rate_native_p2 \
    --executable /workspace/physics_app/physics-opt \
    --p1-identity /workspace/experiments/Issue402_plasma_dsl_g1/evidence/native_p1_identity.json
' 2>&1 | tee "$EVIDENCE/issue402_json_rate_native_p2.log"
echo "ISSUE402_JSON_RATE_SHARED_NATIVE_P2_PASS"

# Issue #541 task #3: genuine FEM signed-charge residual-response discriminator.
# Separate synthetic one-step P3 control: not public S6 or science acceptance.
# The P1 executable, OCI and exact source must match this job's identity receipt.
docker run --rm --entrypoint /bin/bash --user 0:0 \
  --workdir /workspace -v "$PWD:/workspace" \
  -e "EXPECTED_HEAD=$(git rev-parse HEAD)" \
  -e "PINNED_BASE=$PINNED_BASE" "$PINNED_BASE" -lc '
  set -euo pipefail
  source /environment
  git config --global --add safe.directory /workspace
  python3 -m physics_app.ci.check_issue402_signed_fem_residual_native \
    --self-test
  python3 -m physics_app.ci.check_issue402_signed_fem_residual_native \
    --executable /workspace/physics_app/physics-opt \
    --p1-identity /workspace/experiments/Issue402_plasma_dsl_g1/evidence/native_p1_identity.json \
    --expected-head "$EXPECTED_HEAD" --oci-image "$PINNED_BASE" \
    --output-dir /workspace/experiments/Issue402_plasma_dsl_g1/evidence/charge_residual
' 2>&1 | tee "$EVIDENCE/issue541_task3_charge_residual_native.log"
test -s "$EVIDENCE/charge_residual/receipt.json"
echo "ISSUE541_TASK3_JSON_SIGNED_FEM_RESIDUAL_NATIVE_VERIFIED"




native --check-input -i "$PILOT/baseline.i" \
  2>&1 | tee "$EVIDENCE/baseline_check.log"
# JSON-owned log-molar solver variables and initial density: standalone P2 only.
# Legacy baseline.i declares external variables/ICs and cannot be overlaid.
native --check-input -i "$PILOT/valid_bindings.i" \
  2>&1 | tee "$EVIDENCE/valid_bindings_check.log"
# Verify canonical names e/O2p/Om/Op through the JSON-owned four-species P2 fixture.
# Preserve the older generic_four_species.i as historical input evidence.
native --check-input -i "$PILOT/species_density_pairs_p2.i" \
  2>&1 | tee "$EVIDENCE/generic_four_species_check.log"
echo "PLASMA_GENERIC_SPECIES_STATE_NAMES_P2_PASS"
# Distinct synthetic full-Action P2: JSON creates selected e/O2p initial states
# and Physics owns the electron energy/Poisson/RF kernels. Never merge baseline.
native --check-input -i "$PILOT/valid_all_physics_json_p2.i" \
  2>&1 | tee "$EVIDENCE/all_physics_check.log"
echo "PLASMA_ALL_PHYSICS_JSON_OWNED_P2_PASS"
# Standalone positive construction check: one generated FEM transport Kernel.
# It is a P2-only input, not an accepted physical simulation or P3 parity run.
# Modern generated option-first transport uses a standalone JSON-owned
# electron log-molar IC. The retired baseline overlay remains as source history.
native --check-input -i "$PILOT/valid_generated_transport_json_p2.i" \
  2>&1 | tee "$EVIDENCE/valid_generated_transport_options.log"
echo "PLASMA_OPTION_ONLY_FEM_GENERATION_P2_PASS"

# Automatic species-based DDTransportMaterial and JSON-sourced NVTransportMaterial.
# No transport-coefficient [FunctorMaterials] declarations in this deck.
native --check-input -i "$PILOT/valid_json_generated_transport.i" \
  2>&1 | tee "$EVIDENCE/json_generated_transport_check.log"
echo "PLASMA_JSON_TRANSPORT_GENERATION_P2_PASS"
# AD-preserving DDTransportMaterial model=functor generated directly from JSON.
native --check-input -i "$PILOT/valid_json_generated_functor.i" \
  2>&1 | tee "$EVIDENCE/json_generated_functor_check.log"
echo "PLASMA_JSON_FUNCTOR_TRANSPORT_GENERATION_P2_PASS"
# Single-provider checks: DDTransportMaterial creates canonical ion mu/D; the
# separate charge-density Material owns n_i and Poisson-source Functors.
# The retired charge-transport assembler is not instantiated.
native --check-input -i "$PILOT/charge_core_ddmaterial_owner_p2.i" \
  2>&1 | tee "$EVIDENCE/charge_core_ddmaterial_owner_p2.log"
echo "PLASMA_DDMATERIAL_ION_COEFFICIENT_SINGLE_OWNER_P2_PASS"

# Retired charge-transport assembler must not remain factory-registered.
set +e
native --check-input -i "$PILOT/invalid_retired_charge_material_p2.i" \
  > "$EVIDENCE/invalid_retired_charge_material_p2.log" 2>&1
retired_charge_status=$?
set -e
if [[ "$retired_charge_status" -eq 0 ]] || \
   ! grep -Fq "PlasmaChargeTransportMaterial" "$EVIDENCE/invalid_retired_charge_material_p2.log"; then
  echo "::error::Retired charge transport factory type unexpectedly accepted" >&2
  cat "$EVIDENCE/invalid_retired_charge_material_p2.log" >&2
  exit 30
fi
echo "PLASMA_RETIRED_CHARGE_ASSEMBLER_REJECTED"

# FEM Poisson must consume charge_density / epsilon_0 as an AD Functor
# with an RHS FunctorKernel, without requiring a FE MaterialProperty adapter.
native --check-input -i "$PILOT/valid_fem_poisson_charge_functor_p2.i" \
  2>&1 | tee "$EVIDENCE/fem_poisson_charge_functor_p2.log"
echo "PLASMA_FEM_POISSON_CHARGE_FUNCTOR_P2_PASS"

# The existing FE MaterialProperty path must never be combined with the
# Functor path, because it would count the charge density twice.
set +e
native --check-input -i "$PILOT/invalid_fem_poisson_dual_source_p2.i" \
  > "$EVIDENCE/invalid_fem_poisson_dual_source_p2.log" 2>&1
poisson_dual_status=$?
set -e
if [[ "$poisson_dual_status" -eq 0 ]] || \
   ! grep -Fq "Poisson may have only one charge RHS owner" "$EVIDENCE/invalid_fem_poisson_dual_source_p2.log"; then
  echo "::error::FEM Poisson allowed duplicate charge source owners" >&2
  cat "$EVIDENCE/invalid_fem_poisson_dual_source_p2.log" >&2
  exit 31
fi
echo "PLASMA_FEM_POISSON_DUAL_SOURCE_REJECTED"
# Only Material logic may derive canonical mobility/diffusivity names.
set +e
native --check-input -i "$PILOT/invalid_json_functor_name_override_p2.i" \
  > "$EVIDENCE/invalid_json_functor_name_override_p2.log" 2>&1
bad_functor_status=$?
set -e
if [[ "$bad_functor_status" -eq 0 ]] || \
   ! grep -Fq "functor transport forbids mobility_source" "$EVIDENCE/invalid_json_functor_name_override_p2.log"; then
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
             "invalid_json_dd_bad_lookup_p2:DDTransportMaterial lookup coefficients must be finite and nonnegative"; do
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

# JSON species initial_number_density generates FEM/FV variables and log-molar ICs.
# These are parser/P2 checks only; no P3 or physical S6 run.
native --check-input -i "$PILOT/species_density_pairs_p2.i" \
  2>&1 | tee "$EVIDENCE/species_density_pairs_p2.log"
echo "PLASMA_JSON_SPECIES_INITIAL_P2_PASS"
# Physics-generated energy/potential states, exact-head P2 check only.
native --check-input -i "$PILOT/auto_energy_potential_p2.i" \
  2>&1 | tee "$EVIDENCE/auto_energy_potential_p2.log"
echo "PLASMA_AUTO_ENERGY_POTENTIAL_P2_PASS"
for entry in "invalid_auto_energy_missing_initial_p2:requires either explicit .i initial_molar_energy_density_eV or species.e initial_number_density and positive temperature_eV in JSON" \
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

for entry in "invalid_species_density_zero_p2:Invalid species ID for automatic naming: 0" \
             "invalid_species_density_odd_p2:Invalid species ID for automatic naming: 1e16" \
             "invalid_species_density_nan_p2:Selected species 'nan' requires species.nan.initial_number_density"; do
  item="${entry%%:*}"
  expected="${entry#*:}"
  set +e
  native --check-input -i "$PILOT/$item.i" > "$EVIDENCE/$item.log" 2>&1
  result=$?
  set -e
  if [[ "$result" -eq 0 ]] || ! grep -Fq "$expected" "$EVIDENCE/$item.log"; then
    echo "::error::Retired positional species initial or missing JSON species was accepted: $item" >&2
    cat "$EVIDENCE/$item.log" >&2
    exit 25
  fi
done
echo "PLASMA_RETIRED_POSITIONAL_SPECIES_INITIAL_REJECTED"


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

# Issue #633 P14: actual source-bound 3-ion FV Kernel generation P2.
# These are synthetic, deliberately nonphysical Rate values; --check-input
# exercises Factory + TheWarehouse 12/12 uniqueness, NOT P3 science.
native --check-input -i "$PILOT/chemistry_s6_417_three_ion_fv_generated_p2.i" \
  2>&1 | tee "$EVIDENCE/issue633_fv12_generated_p2.log"
echo "ISSUE633_FV_KERNEL_12_NATIVE_P2_PASS_NOT_SCIENCE"

# P05: the same Physics generation must reject a competing Native Kernel.
set +e
native --check-input -i "$PILOT/chemistry_s6_417_three_ion_fv_generated_p2.i" \
  "$PILOT/chemistry_s6_417_three_ion_fv_duplicate_p2.i" \
  > "$EVIDENCE/issue633_native_duplicate_negative_p2.log" 2>&1
issue633_duplicate_rc=$?
set -e
if [[ "$issue633_duplicate_rc" -eq 0 ]] ||
   ! grep -Fq "P05 FV Native/Physics duplicate or unexpected owner" \
     "$EVIDENCE/issue633_native_duplicate_negative_p2.log"; then
  echo "::error::Issue633 P05 accepted Native/Physics duplicate or failed before P05" >&2
  cat "$EVIDENCE/issue633_native_duplicate_negative_p2.log" >&2
  exit 42
fi
echo "ISSUE633_FV_NATIVE_DUPLICATE_REJECTED_P2_PASS"

# Negative P2: no second Native time derivative alongside generated e_time.
# This checks semantic Kernel type + variable ownership, not object name only.
set +e
# The current JSON-owned P2 generates exactly one e_time. Overlay an
# intentionally duplicate Native kernel without the retired external IC deck.
native --check-input -i "$PILOT/valid_generated_transport_json_p2.i" \
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
  # The obsolete fem_kernel_names option must be checked against the modern
  # JSON-owned generated transport input; old baseline masks it via missing IC.
  if [[ "$item" == invalid_legacy_kernel_names || "$item" == invalid_missing_fvm_charges ||
        "$item" == invalid_incomplete_coefficients || "$item" == invalid_wrong_charge_sign ]]; then
    input_decks=("$PILOT/valid_generated_transport_json_p2.i" "$PILOT/$item.i")
  else
    input_decks=("$PILOT/baseline.i" "$PILOT/$item.i")
  fi
  set +e
  native --check-input -i "${input_decks[@]}" \
    > "$EVIDENCE/$item.log" 2>&1
  code=$?
  set -e
  case "$item" in
    invalid_overlap) expected='species listed in both groups' ;;
    invalid_fem_fv_swap) expected="Species 'O2p' has JSON initial_number_density and an existing solver variable 'log_O2p'" ;;
    invalid_no_species) expected='List at least one species' ;;
    invalid_energy_species) expected="Electron energy requires fem_species" ;;
    invalid_chemistry_reactions) expected='duplicate reaction ID or generated progress owner' ;;
    invalid_poisson_variable) expected='Poisson fem_potential requires an FEM solver variable' ;;
    invalid_maxwell_frequency) expected='The frequency must be greater than zero' ;;
    invalid_missing_variable) expected="Selected species 'missing' requires species.missing.initial_number_density" ;;
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
# Tiny diffusion parity is an intentionally different contract: adding an
# otherwise inert root Action must NOT modify the external Native equations.
# The archived all-physics overlay is no longer valid as a no-op numerical run.
native -i "$PILOT/baseline.i" "$PILOT/noop_physics_root_overlay.i" \
  "Outputs/file_base=$EVIDENCE/candidate/plasma" \
  2>&1 | tee "$EVIDENCE/candidate_run.log"
test -s "$EVIDENCE/baseline/plasma.e"
test -s "$EVIDENCE/candidate/plasma.e"
python3 "$PILOT/compare_native_outputs.py" \
  --baseline "$EVIDENCE/baseline/plasma.e" \
  --candidate "$EVIDENCE/candidate/plasma.e" \
  --output "$EVIDENCE/numerical_parity.json"
echo "PLASMA_RESULTS_MATCH"

# #5: mutate COPIES of the actual physics-opt-produced Exodus files and prove
# that the same exact-head comparator rejects false parity. The native outputs
# and original scientific inputs remain untouched. This is the tiny-fixture
# contract only, never full S6/P3 scientific equivalence.
python3 - "$EVIDENCE" "$PILOT/compare_native_outputs.py" "$(git rev-parse HEAD)" <<'PY'
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from scipy.io import netcdf_file

evidence, oracle, head = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
baseline = evidence / "baseline/plasma.e"
candidate = evidence / "candidate/plasma.e"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


before = {"baseline": sha(baseline), "candidate": sha(candidate)}
receipt = {
    "schema": "issue541.native_parity_negative_controls.v1",
    "source_sha": head,
    "baseline_exodus_sha256": before["baseline"],
    "candidate_exodus_sha256": before["candidate"],
    "scope": "actual tiny Native diffusion output, not S6/P3/science",
    "result": "NOT_EVALUATED",
    "controls": {},
}

with tempfile.TemporaryDirectory(prefix="issue541_parity_", dir=evidence) as workspace:
    scratch = Path(workspace)

    def must_reject(case, ref_file, candidate_file, expected_reason):
        report_path = scratch / (case + ".json")
        process = subprocess.run(
            [sys.executable, str(oracle), "--baseline", str(ref_file),
             "--candidate", str(candidate_file), "--output", str(report_path)],
            capture_output=True, text=True, check=False)
        if not report_path.is_file():
            raise RuntimeError(f"{case}: comparator did not produce a report")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if (process.returncode == 0 or
                report.get("result") != "NATIVE_PARITY_NOT_PROVEN" or
                expected_reason not in report.get("reason", "")):
            raise RuntimeError(
                f"{case}: invalid Native Exodus data accepted/misdiagnosed: "
                f"exit={process.returncode}, report={report}, stderr={process.stderr}")
        receipt["controls"][case] = {
            "status": "PASS_EXPECTED_REJECTION",
            "reason": report["reason"],
            "baseline_sha256": sha(ref_file),
            "candidate_sha256": sha(candidate_file),
        }

    # Negative 1: change one physical state value in an actual solver output.
    # This is not a synthetic netCDF file or a parser-only check.
    perturbed = scratch / "perturbed_candidate.e"
    shutil.copyfile(candidate, perturbed)
    with netcdf_file(perturbed, "a", mmap=False) as exodus:
        names = sorted(name for name in exodus.variables
                       if name.startswith("vals_nod_var")
                       and name[len("vals_nod_var"):].isdigit())
        if not names:
            raise RuntimeError("No actual Native nodal state available to perturb")
        values = np.array(exodus.variables[names[0]].data, copy=True)
        if not values.size or not np.isfinite(values).all():
            raise RuntimeError("No finite Native state to perturb")
        original = float(values.flat[0])
        values.flat[0] = original + 1.0 + abs(original) * 1e-3
        exodus.variables[names[0]][:] = values
    if sha(perturbed) == before["candidate"]:
        raise RuntimeError("Native perturbation did not change Exodus bytes")
    must_reject("numeric_state_mutation", baseline, perturbed,
                "Numerical discrepancy")

    # Negative 2: a new unrecognised physical field in BOTH outputs must
    # not be silently skipped just because the inventories still match.
    first = scratch / "extra_reference.e"
    second = scratch / "extra_candidate.e"
    shutil.copyfile(baseline, first)
    shutil.copyfile(baseline, second)
    for path in (first, second):
        with netcdf_file(path, "a", mmap=False) as exodus:
            name = "vals_nset_var1ns1"
            if name in exodus.variables or "time_whole" not in exodus.variables:
                raise RuntimeError("Unexpected original Native output layout")
            times = exodus.variables["time_whole"]
            extra = exodus.createVariable(name, "d", times.dimensions)
            extra[:] = np.zeros_like(np.asarray(times.data), dtype=float)
    must_reject("same_unrecognised_physical_field", first, second,
                "Unsupported Exodus physical field")

# Guard original Native provenance against mutation during negative controls.
if sha(baseline) != before["baseline"] or sha(candidate) != before["candidate"]:
    raise RuntimeError("Native parity negative control modified original output")
if set(receipt["controls"]) != {
    "numeric_state_mutation", "same_unrecognised_physical_field"
}:
    raise RuntimeError("Native parity negative control coverage incomplete")
receipt["result"] = "NATIVE_PARITY_FALSE_PASS_REJECTED"
(evidence / "native_parity_negative_controls.json").write_text(
    json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(receipt["result"])
PY

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
