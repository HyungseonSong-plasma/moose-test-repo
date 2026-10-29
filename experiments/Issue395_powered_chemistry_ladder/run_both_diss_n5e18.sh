#!/usr/bin/env bash
# Pinned Issue397 1000W physics; both dissociation channels plus optional EDETACH.
set -euo pipefail
PHASE="$1"
case "$PHASE" in check|solve) ;; *) echo "check or solve only" >&2; exit 2;; esac
case "$EDETACH_OM" in on|off) ;; *) echo "EDETACH_OM must be on/off" >&2; exit 2;; esac
test "$PURE_O2_INLET" = 1
test "$DISS_CHANNEL" = ground
test "$(git rev-parse HEAD)" = "aa81c1ca1d52e9431b56682b227fe96aa3a305cd"
CHEM=experiments/Issue395_powered_chemistry_ladder
BASE="$CHEM/rf_elastic_diss_ion_ei20_ei01_1000w_adjacent_sheath_wall_closed_100us_dt1000ns"
INPUT="$BASE.i"
RESULT="$BASE""_pure_o2_inlet_step1"
PARENT="$CHEM/rf_elastic_multiapp_parent_1000w_100us_dt1000ns_overlay.i"
ELASTIC="$CHEM/o2_elastic_1000w_100us_dt1000ns_overlay.i"
GROUND="$CHEM/o2_dissociation_1000w_100us_dt1000ns_overlay.i"
MIXED="$CHEM/o2_dissociation_mixed_1000w_100us_dt1000ns_overlay.i"
ION="$CHEM/o2_ionization_1000w_100us_dt1000ns_overlay.i"
ION_O="$CHEM/o_ionization_ei20_1000w_100us_dt1000ns_overlay.i"
ATTACH="$CHEM/o2_attachment_ei01_1000w_100us_dt1000ns_overlay.i"
OELASTIC="$CHEM/o_elastic_ei17_1000w_100us_dt1000ns_overlay.i"
DETACH="$CHEM/o_minus_e_detachment_1000w_100us_dt1000ns_overlay.i"
for f in "$INPUT" "$PARENT" "$ELASTIC" "$GROUND" "$MIXED" "$ION" "$ION_O" "$ATTACH" "$OELASTIC" "$DETACH"; do test -s "$f"; done
python3 "$CHEM/set_pure_o2_inlet.py" --input "$INPUT" --verify
python3 "experiment-driver/$CHEM/set_o3p_initial_density_experiment.py" --input "$INPUT" --target-number-density 5e18 --verify
if [[ "$EDETACH_OM" = off ]]; then
  grep -Fqx '# Case A: EDETACH_OM explicitly disabled.' "$DETACH"
else
  grep -Fqx '    property_name = R_detach_Om' "$DETACH"
fi
grep -Fqx '    property_name = R_diss_O2' "$GROUND"
grep -Fqx '    property_name = R_diss_O2_mixed' "$MIXED"
BUILD_BASE_REF="ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"
mkdir -p "$RESULT/run"
mode=""
output=""
if [[ "$PHASE" = check ]]; then mode="--check-input"; output="$RESULT/check_input.log"
else output="$RESULT/runtime.log"; fi
docker run --rm --entrypoint /bin/bash --user 0:0 \
  --workdir /workspace -v "$GITHUB_WORKSPACE:/workspace" "$BUILD_BASE_REF" -lc "
    set -euo pipefail
    source /environment
    physics_app/physics-opt $mode \
      -i '$INPUT' \
      '$PARENT' \
      '$ELASTIC' \
      '$GROUND' \
      '$MIXED' \
      '$ION' \
      '$ION_O' \
      '$ATTACH' \
      '$OELASTIC' \
      '$DETACH' \
      Outputs/file_base='$RESULT/run/plasma'
  " 2>&1 | tee "$output"
echo "BOTH_DISS_EDETACH_EDETACH_OM_PHASE_PASS"
