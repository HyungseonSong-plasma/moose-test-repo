#!/usr/bin/env python3
"""Build the Issue #234 one-way Poisson observer with only automatic-scaling controls changed."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
OBSERVER_ROOT = ROOT.parent / "Issue234_m1_1d_poisson_observer"
sys.path.insert(0, str(OBSERVER_ROOT))

from build import BASE, build, static_contract_text  # noqa: E402

OUT = ROOT / "input_poisson_observer_scaled.i"

UNSCALED = """  automatic_scaling = false
"""
SCALED = """  automatic_scaling = true
  off_diagonals_in_auto_scaling = true
  compute_scaling_once = true
"""


def build_scaled() -> str:
    candidate = build(BASE.read_text(encoding="utf-8"))
    if candidate.count(UNSCALED) != 1:
        raise RuntimeError(
            f"expected exactly one unscaled Executioner anchor, got {candidate.count(UNSCALED)}"
        )
    scaled = candidate.replace(UNSCALED, SCALED, 1)

    # Physics/model identity guard: stripping the three scaling controls must recover
    # byte-identical unscaled candidate text.
    recovered = scaled.replace(SCALED, UNSCALED, 1)
    if recovered != candidate:
        raise RuntimeError("scaled candidate changes more than the declared scaling controls")

    checks = static_contract_text(scaled)
    # The inherited observer contract intentionally expects automatic_scaling=false;
    # all other scientific/construction checks must still hold.
    allowed_false = {"automatic_scaling_off"}
    failed = {name for name, ok in checks.items() if not ok}
    if failed != allowed_false:
        raise RuntimeError(f"unexpected scaled-candidate contract differences: {sorted(failed)}")

    required = {
        "automatic_scaling_on": "automatic_scaling = true" in scaled,
        "off_diagonal_scaling_on": "off_diagonals_in_auto_scaling = true" in scaled,
        "compute_scaling_once": "compute_scaling_once = true" in scaled,
        "poisson_feedback_still_off": "potential = potential_plasma" not in scaled,
        "prescribed_drift_still_on": "potential = phi_ramp" in scaled,
    }
    bad = sorted(k for k, ok in required.items() if not ok)
    if bad:
        raise RuntimeError(f"scaled numerical contract failed: {bad}")
    return scaled


def self_test() -> None:
    scaled = build_scaled()

    # Mutation control: switching the drift potential to the solved Poisson field must
    # be detectable as a physics/coupling change and is not part of this discriminator.
    mutated = scaled.replace("potential = phi_ramp", "potential = potential_plasma", 1)
    if "potential = potential_plasma" not in mutated:
        raise RuntimeError("feedback mutation control was not constructed")
    if mutated == scaled:
        raise RuntimeError("feedback mutation control is a no-op")


def main() -> int:
    self_test()
    text = build_scaled()
    OUT.write_text(text, encoding="utf-8")
    print(f"WROTE {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
