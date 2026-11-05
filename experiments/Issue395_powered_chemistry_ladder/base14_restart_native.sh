#!/usr/bin/env bash
# Original Oxygen14 BASE: one genuine advanced restart, 100us to 300us.
# Run only in the pinned native build container, never reconstruct from CSV.
set -euo pipefail
mode="${1:?check or solve}"
power="${2:?400 or 1000}"
case "$mode" in check|solve) ;; *) echo "invalid restart mode" >&2; exit 2;; esac
case "$power" in 400|1000) ;; *) echo "invalid BASE power" >&2; exit 2;; esac
cd /workspace
source /environment
CHEM=experiments/Issue395_powered_chemistry_ladder
tag="${power}w_100us_dt1000ns"
RESULT="$CHEM/results_rf_elastic_diss_ion_ei20_ei01_${power}w_adjacent_sheath_wall_closed_100us_dt1000ns"
INPUT="$CHEM/rf_elastic_diss_ion_ei20_ei01_${power}w_adjacent_sheath_wall_closed_100us_dt1000ns.i"
PARENT="$CHEM/rf_elastic_multiapp_parent_${tag}_overlay.i"
args=(
  "$INPUT"
  "$PARENT"
  "$CHEM/o2_elastic_${tag}_overlay.i"
  "$CHEM/o2_dissociation_ei412_${tag}_overlay.i"
  "$CHEM/o2_ionization_ei415_${tag}_overlay.i"
  "$CHEM/o_ionization_ei941_${tag}_overlay.i"
  "$CHEM/o2_attachment_ei401_${tag}_overlay.i"
  "$CHEM/o_elastic_ei17_${tag}_overlay.i"
  "$CHEM/ei2738_detachment_formula_${tag}_overlay.i"
  "$CHEM/ei407_only_${tag}_overlay.i"
  "$CHEM/ei417_without_h05_${tag}_overlay.i"
  "$CHEM/ei935_atomic_excitation_${tag}_overlay.i"
  "$CHEM/h24_om_o2p_mutual_neutralization_${tag}_overlay.i"
  "$CHEM/h25_op_o2_charge_transfer_${tag}_overlay.i"
  "$CHEM/h23_op_om_mutual_neutralization_${tag}_overlay.i"
  "$CHEM/ei2069_o2a_dissociation_${tag}_overlay.i"
)
test "${#args[@]}" -eq 16
test -s "$RESULT/recovery_prefix.txt"
checkpoint="$(cat "$RESULT/recovery_prefix.txt")"
test -s "$checkpoint-restart-0.rd/data"
test -s "$checkpoint-mesh.cpa.gz/1/header.gz"
test -s "$CHEM/private_rates/EI-415_O2_X.txt"
test ! -e "$CHEM/private_rates/EI-943_O_1D.txt"
for arg in "${args[@]}"; do test -s "$arg"; done
if [ "$mode" = check ]; then
  exec physics_app/physics-opt --check-input -i "${args[@]}" \
    MultiApps/maxwell_t6/no_restore=false \
    Problem/restart_file_base="/workspace/$checkpoint"
fi
exec physics_app/physics-opt -i "${args[@]}" \
  Outputs/file_base="$RESULT/run/plasma_restart_100000to300000" \
  MultiApps/maxwell_t6/no_restore=false \
  Problem/restart_file_base="/workspace/$checkpoint"
