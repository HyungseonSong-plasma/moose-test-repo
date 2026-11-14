#!/usr/bin/env bash
# Native P2 only: public historical 400 W mesh, public Boltzmann tables and
# the exact option-first PhysicsApp binary built in this same checkout/job.
# Never runs a native timestep, reads protected rates or publishes raw fields.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
PILOT=experiments/Issue402_plasma_dsl_g1
EVIDENCE="$PILOT/evidence"
mkdir -p "$EVIDENCE"
SOURCE_SHA=29d1acc6ef7969908b86719e4b95c73a1565136d
# Match the pinned public Issue #493 400 W research-only preparation flags.
# The historical replay script rejects 400 W unless this explicit opt-in is set.
export OXYGEN_RESEARCH_400=1
export OXYGEN_RESEARCH_FULL24=0
export OXYGEN_RESEARCH_EI2738_FORMULA=0
export OXYGEN_RESEARCH_QUICK_5MIN=0
EXPECTED_HEAD="$(git rev-parse HEAD)"
test -x physics_app/physics-opt
test ! -e "$PILOT/evidence/issue402_option_s6_p2_status.json"

TEMP_PARENT="${RUNNER_TEMP:-/tmp}"
TEMP_ROOT="$(mktemp -d "$TEMP_PARENT/issue402-public-s6.XXXXXXXX")"
trap 'rm -rf "$TEMP_ROOT"' EXIT
HIST="$TEMP_ROOT/historical"
git clone --quiet --filter=blob:none --no-checkout \
  https://github.com/HyungseonSong-plasma/moose-test-repo.git "$HIST"
git -C "$HIST" checkout --quiet "$SOURCE_SHA"
test "$(git -C "$HIST" rev-parse HEAD)" = "$SOURCE_SHA"
CHEM=experiments/Issue395_powered_chemistry_ladder
SRC="$HIST/.github/oxygen25_eedf/initial_mixture_23xsec_transport.txt"
DST="$HIST/experiments/Issue91_real_qvt_r3/r3_e0/electron_moments.txt"
test -f "$SRC"
test "$(sha256sum "$SRC" | cut -d' ' -f1)" = \
  35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b
test ! -e "$HIST/$CHEM/private_rates"
cp "$SRC" "$DST"

# Match the already-validated public Issue #493 P2 mesh preparation contract.
python3 -m pip install --disable-pip-version-check --quiet \
  numpy==2.1.2 scipy==1.14.1 matplotlib==3.9.2
(
  cd "$HIST"
  export CHATGPT_WORK_BASE_SHA="$SOURCE_SHA"
  bash "$CHEM/issue397_l1_power_scan_replay.sh" prepare 400
  python3 .github/scripts/oxygen_legacy6_latest_100us.py --power-w 400 --prepare
)
test -s "$HIST/$CHEM/baseline_plasma_plus_unstructured_cover_plus_wafer.msh"
test ! -e "$HIST/$CHEM/private_rates"

# No secrets or historical rate sources. Exact candidate HEAD and built
# binary hashes are recorded and checked for every --check-input invocation.
python3 "$PILOT/public_option_s6_p2.py" \
  --historical "$HIST" --binary "$ROOT/physics_app/physics-opt" \
  --expected-head "$EXPECTED_HEAD" --evidence "$EVIDENCE"
echo ISSUE402_OPTION_ONLY_S6_417_941_PUBLIC_P2_PASS

# Additional no-timestep P2: real S6 channel-rate providers, replacing nine
# legacy electron chemistry source Kernels in disposable scratch only.
python3 "$PILOT/public_chemistry_s6_p2.py" \
  --historical "$HIST" --binary "$ROOT/physics_app/physics-opt" \
  --expected-head "$EXPECTED_HEAD" --evidence "$EVIDENCE"
echo ISSUE402_CHEMISTRY_S6_417_941_PUBLIC_P2_PASS
