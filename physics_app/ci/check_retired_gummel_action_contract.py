#!/usr/bin/env python3
"""Fail closed if the retired GummelIteration input Action returns to PhysicsApp.

Historical input fixtures and research documents may still reference Gummel,
but no current runtime registration or compiled Gummel Action is permitted.
"""
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
print("RETIRED_GUMMEL_ACTION_CONTRACT: PASS")
