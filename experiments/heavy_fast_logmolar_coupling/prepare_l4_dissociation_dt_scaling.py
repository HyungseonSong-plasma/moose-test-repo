#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

import prepare_l4_dt_compare as core
import prepare_l4_dt_ramp_dissociation_20ns as diss

HERE = Path(__file__).resolve().parent
GROUNDED_BOUNDARIES = (
    "inlet outlet plasma_electrode plasma_metal plasma_right plasma_cover "
    "plasma_wafer plasma_focus_ring"
)

CASE_CONFIG = {
    "dt0p1_0p2": (1.0e-10, 2.0e-10),
    "dt0p2_0p4": (2.0e-10, 4.0e-10),
    "dt0p4_0p8": (4.0e-10, 8.0e-10),
    "dt0p8_1p6": (8.0e-10, 1.6e-9),
}
CASES = tuple(CASE_CONFIG)


def _times(dt1: float, dt2: float) -> tuple[float, ...]:
    first = [i * dt1 for i in range(101)]
    t_switch = 100.0 * dt1
    second = [t_switch + j * dt2 for j in range(1, 51)]
    return tuple(first + second)


def _set_time_schedule(text: str, dt1: float, dt2: float) -> str:
    times = _times(dt1, dt2)
    if len(times) != 151:
        raise RuntimeError("expected 150 steps plus t=0")
    end_time = times[-1]

    start, end = core.executioner_bounds(text)
    section = text[start:end]

    # Remove scalar/adaptive timestep controls inherited from the base.
    for name in ("dt", "dtmin", "dtmax", "num_steps"):
        section = re.sub(rf"(?m)^\s*{name}\s*=.*\n", "", section)

    # Remove inherited TimeSequenceStepper and replace it with this case.
    section = re.sub(
        r"(?ms)\n  \[TimeStepper\]\n.*?\n  \[\]\n",
        "\n",
        section,
    )

    if re.search(r"(?m)^\s*end_time\s*=", section):
        section = re.sub(
            r"(?m)^\s*end_time\s*=.*$",
            f"  end_time = {end_time:.17g}",
            section,
        )
    else:
        raise RuntimeError("missing Executioner end_time")

    seq = " ".join(f"{t:.17g}" for t in times)
    ts_block = (
        "\n  [TimeStepper]\n"
        "    type = TimeSequenceStepper\n"
        f"    time_sequence = '{seq}'\n"
        "  []\n"
    )
    close = section.rfind("[]")
    if close < 0:
        raise RuntimeError("cannot locate Executioner closing block")
    section = section[:close] + ts_block + section[close:]

    text = text[:start] + section + text[end:]
    return text


def build(case: str) -> Path:
    if case not in CASES:
        raise ValueError(case)

    dt1, dt2 = CASE_CONFIG[case]

    # Base physics: Ti=Te=2 eV, ne=nO2+=1e15 m^-3,
    # O2 ionization ON + O2 dissociation ON.
    base = diss.build()
    text = base.read_text(encoding="utf-8")

    # Keep the successful sheath/Joule separation diagnostic.
    text = core.set_child_parameter(
        text,
        "energy_joule",
        "suppress_joule_on_boundaries",
        f"'{GROUNDED_BOUNDARIES}'",
    )
    text = _set_time_schedule(text, dt1, dt2)

    times = _times(dt1, dt2)
    end_time = times[-1]
    seq = " ".join(f"{t:.17g}" for t in times)

    required = (
        "type = PhysicsElectronImpactIonizationMaterial",
        "type = PhysicsElectronImpactDissociationMaterial",
        "v = R_ion_O2",
        "coef = -12.06",
        "v = R_diss_O2",
        "coef = -6.0",
        "ion_temperature_eV = 2.0",
        "type = PhysicsFVElectronEnergyJouleHeating",
        f"suppress_joule_on_boundaries = '{GROUNDED_BOUNDARIES}'",
        "type = TimeSequenceStepper",
        f"time_sequence = '{seq}'",
        f"end_time = {end_time:.17g}",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"dt-scaling contract missing: {token}")

    if "axis" in GROUNDED_BOUNDARIES or "x=0" in GROUNDED_BOUNDARIES:
        raise RuntimeError("symmetry axis must not be a Joule-suppression boundary")

    out = HERE / f"full_monolithic_l4_dissociation_joule_suppression_{case}.i"
    out.write_text(text, encoding="utf-8")

    print(f"wrote {out}")
    print(f"case={case}")
    print("chemistry=O2 ionization ON + O2 dissociation ON")
    print("wall-layer Joule suppression=ON")
    print("Ti=2 eV; Te=2 eV; initial mean electron energy=3 eV")
    print(f"schedule={dt1*1e9:.1f} ns x100 + {dt2*1e9:.1f} ns x50")
    print(f"steps=150; end_time={end_time*1e9:.1f} ns")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=CASES)
    args = parser.parse_args()
    build(args.case)


if __name__ == "__main__":
    main()
