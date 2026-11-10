#!/usr/bin/env bash
# Fast, independent, public-data-only P0/P1-environment preflight.
# Run before the expensive PhysicsApp Native build; no solver timesteps.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
PILOT=experiments/Issue402_plasma_dsl_g1
EVIDENCE="$PILOT/evidence"
mkdir -p "$EVIDENCE"
IMAGE='ghcr.io/hyungseonsong-plasma/physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008'
test -f "$PILOT/public_option_s6_p2.py"
test -f "$PILOT/run_public_option_s6_p2.sh"
test "$(git rev-parse HEAD)" = "${EXPECTED_SOURCE_HEAD:-$(git rev-parse HEAD)}"
command -v docker >/dev/null
docker info >/dev/null
# The immutable public P0 oracle verifies deck/source SHA, 19 rate
# SHA-256 hashes, active reaction IDs, and input-layer provenance.
python3 experiments/Issue493_s6_boltzmann/public_p2_check.py --control . --mode preflight
docker pull "$IMAGE"
SCRATCH="$(mktemp -d "${RUNNER_TEMP:-/tmp}/issue402-env-gate.XXXXXXXX")"
cleanup() { rm -rf "$SCRATCH"; }
trap cleanup EXIT
# Exercise the *exact* /workspace source bind and /case scratch policies
# used by the post-build P2 job. Root ownership must not leak to the host.
docker run --rm --network none --entrypoint /bin/bash --user 0:0 \
  --workdir /case \
  --mount "type=bind,src=$ROOT,dst=/workspace,readonly" \
  --mount "type=bind,src=$SCRATCH,dst=/case" \
  "$IMAGE" -lc '
    set -euo pipefail
    source /environment
    test -f /workspace/experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py
    mkdir -p /case/.jitcache/nested
    printf test > /case/.jitcache/nested/owned_by_root
    trap "rm -rf /case/.jitcache" EXIT
  '
test ! -e "$SCRATCH/.jitcache"
printf 'ok' > "$SCRATCH/host_writable"
rm "$SCRATCH/host_writable"
# Check host cleanup explicitly; no artifact contains the source checkout,
# staged private-rate path, or any historical protected table bytes.
rmdir "$SCRATCH"
trap - EXIT
python3 - "$EVIDENCE/option_s6_environment.json" "$(git rev-parse HEAD)" "$IMAGE" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
path.write_text(json.dumps({
    "schema": "issue402.option_s6.environment.v1",
    "source_sha": sys.argv[2],
    "image": sys.argv[3],
    "public_p0": "PASS",
    "docker_mount": "PASS",
    "root_scratch_create_and_cleanup": "PASS",
    "host_cleanup": "PASS",
    "P2": "NOT_RUN",
    "P3": "NOT_RUN",
    "science": "SCIENCE_HOLD",
}, indent=2, sort_keys=True) + "\n")
PY
echo ISSUE402_PUBLIC_S6_ENVIRONMENT_PREFLIGHT_PASS
