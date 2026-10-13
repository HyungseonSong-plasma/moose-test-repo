#!/usr/bin/env python3
"""Append the Issue #395 continuous-run source activation control.

The 15 us production trajectory is a single fresh Transient run.  Reaction owners
remain present from t=0, but the A1 residual projections and RF-heating kernel are
disabled through the common 100 ns baseline and enabled for the first staged
continuation step (100 -> 110 ns).
"""
from __future__ import annotations

import argparse
from pathlib import Path

SOURCE_OBJECTS = (
    "Kernel::a1_electron_particle_source",
    "Kernel::a1_electron_energy_source",
    "FVKernel::a1_o2p_source",
    "FVKernel::a1_neutral_mass_source",
    "Kernel::rf_heating_t6",
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument("--start-time", type=float, default=1.05e-7)
    a = p.parse_args()

    if not (1.0e-7 < a.start_time < 1.1e-7):
        raise RuntimeError("start-time must lie strictly between 100 ns and 110 ns")

    text = a.input.read_text(encoding="utf-8")
    required = (
        "[a1_electron_particle_source]",
        "[a1_electron_energy_source]",
        "[a1_o2p_source]",
        "[a1_neutral_mass_source]",
    )
    missing = [token for token in required if token not in text]
    if missing:
        raise RuntimeError(f"A1 activation overlay missing source objects: {missing}")
    if "[a1_continuous_source_activation]" in text:
        raise RuntimeError("continuous activation control already present")

    objects = " ".join(SOURCE_OBJECTS)
    text += f"""

[Controls]
  [a1_continuous_source_activation]
    type = TimePeriod
    enable_objects = '{objects}'
    start_time = {a.start_time:.17g}
    execute_on = 'INITIAL TIMESTEP_BEGIN'
  []
[]
"""
    a.input.write_text(text, encoding="utf-8")
    print(
        "ISSUE395_A1_CONTINUOUS_ACTIVATION_PASS "
        f"start_time_s={a.start_time:.17g} source_objects={len(SOURCE_OBJECTS)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
