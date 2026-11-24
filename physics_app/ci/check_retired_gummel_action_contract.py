#!/usr/bin/env python3
"""Fail closed if the retired GummelIteration input Action returns to PhysicsApp.

Archived fixtures and research documents may still reference Gummel,
but no current runtime registration or compiled Gummel Action is permitted.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT / "src/base/PhysicsApp.C").read_text(encoding="utf-8")
assert "GummelIterationAction" not in app, "Retired Gummel Action registered"
assert "GummelIteration/*" not in app, "Retired Gummel syntax registered"

for path in ("src/actions/GummelIterationAction.C",
             "include/actions/GummelIterationAction.h"):
    assert not (ROOT / path).exists(), f"Retired compiled Action still exists: {path}"

# The legacy PlasmaClosures composition Action is retired independently.
assert "PlasmaClosuresAction" not in app
assert "PlasmaClosures/*" not in app
for path in ("src/actions/PlasmaClosuresAction.C",
             "include/actions/PlasmaClosuresAction.h"):
    assert not (ROOT / path).exists(), f"Retired PlasmaClosures Action still exists: {path}"

# The custom potential-iterate convergence owner has also been retired.
# Native MOOSE MultiApps and their built-in convergence objects remain available.
for path in ("src/convergence/DeltaPhiMultiAppConvergence.C",
             "include/convergence/DeltaPhiMultiAppConvergence.h"):
    assert not (ROOT / path).exists(), f"Retired convergence object still exists: {path}"

assert 'registerSyntax("DDContinuityEq",' in app
# Former Action-dependent inputs and runner are preserved as non-executable
# exact-blob provenance, not as current-main CI fixtures.
REPO = ROOT.parent
ARCHIVE = REPO / "docs/provenance/retired_gummel_plasma_closures"
HISTORICAL_FIXTURES = {
    "physics_app/ci/plasma_closures_smoke.i": "99c9a88404398e48f194685c2b4b1ff39b56aca2",
    "physics_app/ci/gummel_plasma_closures_driver.i": "25100d6e14bc6dd0f31b8b5f0c0d3273b5cd7319",
    "physics_app/ci/gummel_plasma_closures_heavy_electron.i": "aeeb853fcbee4893f6250939923c4d583742ddc0",
    "physics_app/ci/gummel_plasma_closures_heavy_main.i": "d2b1317a89bc1a9c2c839f144f6f4f4c77acd186",
    "physics_app/ci/gummel_plasma_closures_heavy_poisson.i": "82b8a02ca622aebd1b5f3dd1e429476b1ed56386",
    "physics_app/ci/gummel_action_smoke.i": "50b153c490363408ecff1414d86f52cb25c6868f",
    "physics_app/ci/gummel_action_poisson.i": "14cfe02839a49775c9964ea0d5a414dd3d662db4",
    "physics_app/ci/gummel_two_subapps_main.i": "690e11bb8c161c3f59234c89dbff8f334e8f81aa",
    "physics_app/ci/gummel_two_subapps_electron.i": "a90fce2edea9d628a173df606b84cecfa5eeb2f8",
    "physics_app/ci/gummel_two_subapps_poisson.i": "f1a447f24e91067b2f38097740526af058928770",
    "experiments/Issue351_10mtorr_fixture/control.py": "069dab040dd1e157c313bd32c7535fef75bb0857",
}
for original, expected in HISTORICAL_FIXTURES.items():
    assert not (REPO / original).exists(), f"Retired active fixture returned: {original}"
    archived = ARCHIVE / (original + ".txt")
    raw = archived.read_bytes()
    actual = hashlib.sha1(f"blob {len(raw)}".encode() + bytes(1) + raw).hexdigest()
    assert actual == expected, f"Historical fixture blob drift: {original}"

print("RETIRED_GUMMEL_ACTION_CONTRACT: PASS")
