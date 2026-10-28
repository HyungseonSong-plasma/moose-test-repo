#!/usr/bin/env bash
# Four-arm experimental DR ON/OFF × 400/1000W; do not merge as production.
# Usage: bash .../run_o2p_dr_ab.sh prepare|build|check|solve|audit 400|1000 off|on
set -euo pipefail
test "$#" -eq 3 || { echo "requires PHASE POWER MODE" >&2; exit 2; }
phase="$1"
power="$2"
mode="$3"
case "$phase" in prepare|build|check|solve|audit) ;; *) echo "unknown phase" >&2; exit 2;; esac
case "$power" in 400|1000) ;; *) echo "power must be 400 or 1000" >&2; exit 2;; esac
case "$mode" in on|off) ;; *) echo "DR mode must be on or off" >&2; exit 2;; esac
test "$(git rev-parse --show-toplevel)" = "$PWD"
if [[ -n "$(printenv CHATGPT_WORK_BASE_SHA || true)" ]]; then
  test "$(git rev-parse HEAD)" = "$CHATGPT_WORK_BASE_SHA"
fi

chem=experiments/Issue395_powered_chemistry_ladder
replay="$chem/issue397_l1_power_scan_replay.sh"
name="rf_elastic_diss_ion_ei20_ei01_"$power"w_adjacent_sheath_wall_closed_100us_dt1000ns"
result="$chem/results_$name"
input="$chem/$name.i"
parent="$chem/rf_elastic_multiapp_parent_"$power"w_100us_dt1000ns_overlay.i"
elastic="$chem/o2_elastic_"$power"w_100us_dt1000ns_overlay.i"
diss="$chem/o2_dissociation_"$power"w_100us_dt1000ns_overlay.i"
ion="$chem/o2_ionization_"$power"w_100us_dt1000ns_overlay.i"
iono="$chem/o_ionization_ei20_"$power"w_100us_dt1000ns_overlay.i"
attach="$chem/o2_attachment_ei01_"$power"w_100us_dt1000ns_overlay.i"
oelastic="$chem/o_elastic_ei17_"$power"w_100us_dt1000ns_overlay.i"
dr="$chem/o2p_dr_"$power"w_100us_dt1000ns_overlay.i"
base_img="ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"

case "$phase" in
  prepare)
    bash "$replay" prepare "$power"
    if [[ "$mode" = on ]]; then
      python3 "$chem/build_o2p_dr_overlay.py" \
        --base-input "$chem/a0_full_icp.i" --output "$dr"
      grep -Fq 'property_name = R_o2p_dr' "$dr"
      grep -Fq 'variable = log_ni' "$dr"
      grep -Fq 'variable = w_O' "$dr"
    else
      test ! -f "$dr" || { echo "OFF arm contains DR overlay" >&2; exit 2; }
    fi
    ;;
  build)
    bash "$replay" build "$power"
    ;;
  check)
    bash "$replay" check "$power"
    if [[ "$mode" = on ]]; then
      test -s "$dr"
      docker run --rm --entrypoint /bin/bash --user 0:0 \
        --workdir /workspace -v "$PWD:/workspace" "$base_img" -lc "
          set -euo pipefail
          source /environment
          physics_app/physics-opt --check-input \
          -i '$input' '$parent' '$elastic' '$diss' '$ion' '$iono' '$attach' '$oelastic' '$dr'
        " 2>&1 | tee "$result/check_input_o2p_dr.log"
    fi
    ;;
  solve)
    if [[ "$mode" = off ]]; then
      bash "$replay" solve "$power"
    else
      test -s "$dr"
      docker run --rm --entrypoint /bin/bash --user 0:0 \
        --workdir /workspace -v "$PWD:/workspace" "$base_img" -lc "
          set -euo pipefail
          source /environment
          physics_app/physics-opt \
          -i '$input' '$parent' '$elastic' '$diss' '$ion' '$iono' '$attach' '$oelastic' '$dr' \
          Outputs/file_base='$result/run/plasma'
        " 2>&1 | tee "$result/runtime.log"
    fi
    ;;
  audit)
    bash "$replay" audit "$power"
    ;;
esac
echo "O2P_DR_AB_STAGE_PASS phase=$phase power_W=$power dr=$mode sha=$(git rev-parse HEAD)"
