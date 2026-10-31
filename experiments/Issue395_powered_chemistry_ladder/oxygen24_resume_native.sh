#!/usr/bin/env bash
# Recover the exact same parent+Maxwell MultiApp and 24 chemistry from a real
# 2 ns MOOSE checkpoint. This is NOT a CSV/Exodus initial-condition reconstruction.
set -euo pipefail
POWER_W="${1:?usage: bash oxygen24_resume_native.sh 400|1000}"
case "$POWER_W" in 400|1000) ;; *) echo "unsupported power" >&2; exit 2;; esac
test "${OXYGEN_RESEARCH_FULL24:-0}" = 1
test "${OXYGEN_RESEARCH_QUICK_5MIN:-0}" = 1
test "$(git rev-parse --show-toplevel)" = "$PWD"
if [[ -n "${CHATGPT_WORK_BASE_SHA:-}" ]]; then
  test "$(git rev-parse HEAD)" = "$CHATGPT_WORK_BASE_SHA"
fi

CHEM="experiments/Issue395_powered_chemistry_ladder"
RESULT="$CHEM/results_rf_elastic_diss_ion_ei20_ei01_${POWER_W}w_adjacent_sheath_wall_closed_100us_dt1000ns"
INPUT="$CHEM/rf_elastic_diss_ion_ei20_ei01_${POWER_W}w_adjacent_sheath_wall_closed_100us_dt1000ns.i"
PARENT="$CHEM/rf_elastic_multiapp_parent_${POWER_W}w_100us_dt1000ns_overlay.i"
ELASTIC="$CHEM/o2_elastic_${POWER_W}w_100us_dt1000ns_overlay.i"
FULL24="$CHEM/full24_${POWER_W}w_100us_dt1000ns_overlay.i"
OELASTIC="$CHEM/o_elastic_ei17_${POWER_W}w_100us_dt1000ns_overlay.i"
BUILD_BASE_REF="ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008"

for item in "$INPUT" "$PARENT" "$ELASTIC" "$FULL24" "$OELASTIC"; do
  test -s "$item" || { echo "missing source or overlay: $item" >&2; exit 2; }
done
test -s "$RESULT/run/plasma_cp/0002-restart-0.rd/data" || { echo "missing exact 2ns restart state" >&2; exit 2; }
test -s "$RESULT/run/plasma_cp/0002-mesh.cpa.gz/1/header.gz" || { echo "missing exact 2ns mesh checkpoint" >&2; exit 2; }

# Output basename must remain identical: --recover resolves its source
# checkpoint from the same parent output path, including MultiApp backups.
# Do not call 'prepare' between checkpoint and recovery.
docker run --rm --entrypoint /bin/bash --user 0:0 \
  --workdir /workspace -v "$PWD:/workspace" "$BUILD_BASE_REF" -lc "
    set -euo pipefail
    source /environment
    physics_app/physics-opt \
      -i '$INPUT' \
      '$PARENT' '$ELASTIC' '$FULL24' '$OELASTIC' \
      Outputs/file_base='$RESULT/run/plasma' \
      --recover '$RESULT/run/plasma_cp/0002'
  " 2>&1 | tee "$RESULT/recovery_runtime.log"

echo "OXYGEN24_NATIVE_MULTIAPP_RECOVERY_COMMAND_PASS=$POWER_W"
