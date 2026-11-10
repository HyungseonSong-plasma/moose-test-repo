#!/usr/bin/env bash
# Bounded actual Native P3 process startup on unchanged 460-step B/D decks.
# Full 460-step parity is NEVER claimed by this watchdog diagnostic.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
PILOT=experiments/Issue402_plasma_dsl_g1
EVIDENCE="$PILOT/evidence"
SOURCE_SHA=29d1acc6ef7969908b86719e4b95c73a1565136d
export OXYGEN_RESEARCH_400=1
export OXYGEN_RESEARCH_FULL24=0
export OXYGEN_RESEARCH_EI2738_FORMULA=0
export OXYGEN_RESEARCH_QUICK_5MIN=0
test -x physics_app/physics-opt
test -f "$EVIDENCE/issue402_option_s6_p2_status.json"
test ! -e "$EVIDENCE/issue402_p3_bounded_probe_status.json"

SCRATCH="$(mktemp -d "${RUNNER_TEMP:-/tmp}/issue402-p3-prepared.XXXXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT
HIST="$SCRATCH/historical"
git clone --quiet --filter=blob:none --no-checkout \
  https://github.com/HyungseonSong-plasma/moose-test-repo.git "$HIST"
git -C "$HIST" checkout --quiet "$SOURCE_SHA"
test "$(git -C "$HIST" rev-parse HEAD)" = "$SOURCE_SHA"
CHEM=experiments/Issue395_powered_chemistry_ladder
SRC="$HIST/.github/oxygen25_eedf/initial_mixture_23xsec_transport.txt"
DST="$HIST/experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
test "$(sha256sum "$SRC" | cut -d' ' -f1)" = \
  35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b
test ! -e "$HIST/$CHEM/private_rates"
cp "$SRC" "$DST"
(
  cd "$HIST"
  export CHATGPT_WORK_BASE_SHA="$SOURCE_SHA"
  bash "$CHEM/issue397_l1_power_scan_replay.sh" prepare 400
  python3 .github/scripts/oxygen_legacy6_latest_100us.py --power-w 400 --prepare
)
test -s "$HIST/$CHEM/baseline_plasma_plus_unstructured_cover_plus_wafer.msh"
test ! -e "$HIST/$CHEM/private_rates"
python3 "$PILOT/public_option_s6_p3_probe.py" \
  --historical "$HIST" \
  --binary "$ROOT/physics_app/physics-opt" \
  --source-sha "$(git rev-parse HEAD)" \
  --evidence "$EVIDENCE" --seconds 90
echo ISSUE402_PUBLIC_S6_P3_BOUNDED_STARTUP_PROBE_RECORDED
