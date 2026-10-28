#!/usr/bin/env bash
# Controlled zero initial atomic-O variation on existing four-arm O2+ DR study.
# Usage: bash run_zero_initial_o2p_dr_ab.sh prepare|build|check|solve|audit 400|1000 off|on
set -euo pipefail
test "$#" -eq 3 || { echo "expected PHASE POWER DR_MODE" >&2; exit 2; }
phase="$1"; power="$2"; dr_mode="$3"
case "$phase" in prepare|build|check|solve|audit) ;; *) echo "invalid phase" >&2; exit 2;; esac
case "$power" in 400|1000) ;; *) echo "invalid power" >&2; exit 2;; esac
case "$dr_mode" in off|on) ;; *) echo "invalid DR mode" >&2; exit 2;; esac
test "$(git rev-parse --show-toplevel)" = "$PWD"
chem=experiments/Issue395_powered_chemistry_ladder
base="$chem/run_o2p_dr_ab.sh"
patcher="$chem/set_zero_initial_atomic_o.py"
input="$chem/rf_elastic_diss_ion_ei20_ei01_"$power"w_adjacent_sheath_wall_closed_100us_dt1000ns.i"

if [[ "$phase" == "prepare" ]]; then
  bash "$base" prepare "$power" "$dr_mode"
  python3 "$patcher" --input "$input"
else
  python3 "$patcher" --input "$input" --verify
  bash "$base" "$phase" "$power" "$dr_mode"
fi
echo "ZERO_INITIAL_O_PHASE_PASS phase=$phase power=$power dr=$dr_mode source_sha=$(git rev-parse HEAD)"
