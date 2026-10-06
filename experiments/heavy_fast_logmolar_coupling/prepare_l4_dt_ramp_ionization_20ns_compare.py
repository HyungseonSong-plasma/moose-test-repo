#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

import prepare_l4_o2_ionization_ab as chem
import prepare_l4_dt_compare as core

HERE = Path(__file__).resolve().parent
TOTAL_TIME = 2.0e-8
CASES = ("ramp_0p1x100_0p2x50", "control_0p1x200")


def _ramp_times() -> tuple[float, ...]:
    # 0 -> 10 ns with 0.1 ns steps (100 steps), then 10 -> 20 ns
    # with 0.2 ns steps (50 steps).
    first = [i * 1.0e-10 for i in range(101)]
    second = [1.0e-8 + j * 2.0e-10 for j in range(1, 51)]
    return tuple(first + second)


TIME_SEQUENCES = {
    "ramp_0p1x100_0p2x50": _ramp_times(),
    "control_0p1x200": tuple(i * 1.0e-10 for i in range(201)),
}

EXPECTED_STEPS = {
    "ramp_0p1x100_0p2x50": 150,
    "control_0p1x200": 200,
}


def _set_time_sequence(text: str, case: str) -> str:
    start, end = core.executioner_bounds(text)
    section = text[start:end]

    for name in ("dt", "dtmin", "dtmax", "num_steps"):
        section = re.sub(rf"(?m)^\s*{name}\s*=.*\n", "", section)

    if re.search(r"(?m)^\s*end_time\s*=", section):
        section = re.sub(
            r"(?m)^\s*end_time\s*=.*$",
            f"  end_time = {TOTAL_TIME:.17g}",
            section,
        )
    else:
        raise RuntimeError("missing inherited end_time")

    times = TIME_SEQUENCES[case]
    if len(times) - 1 != EXPECTED_STEPS[case]:
        raise RuntimeError("unexpected number of time steps")
    if abs(times[-1] - TOTAL_TIME) > 1.0e-20:
        raise RuntimeError("time sequence does not end at 20 ns")

    seq = " ".join(f"{t:.17g}" for t in times)
    block = (
        "\n  [TimeStepper]\n"
        "    type = TimeSequenceStepper\n"
        f"    time_sequence = '{seq}'\n"
        "  []\n"
    )
    close = section.rfind("[]")
    if close < 0:
        raise RuntimeError("cannot locate Executioner closing block")
    section = section[:close] + block + section[close:]
    return text[:start] + section + text[end:]


def build(case: str) -> Path:
    if case not in CASES:
        raise ValueError(case)

    # Same physics as the successful O2-ionization-only monolithic case.
    baseline = chem.build("o2_ionization_on")
    text = baseline.read_text(encoding="utf-8")
    text = _set_time_sequence(text, case)

    required = (
        "type = PhysicsElectronImpactIonizationMaterial",
        "rate_table_file = ../../physics_app/data/electron_impact/o2_ionization.txt",
        "type = PhysicsO2IonizationSourceMaterial",
        "type = PhysicsFVLogMolarElectronReactionSource",
        "number_source = electron_ionization_number_source",
        "source = O2p_ionization_mass_source",
        "v = R_ion_O2",
        "coef = -12.06",
        "type = TimeSequenceStepper",
        f"end_time = {TOTAL_TIME:.17g}",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"20 ns discriminator missing required token: {token}")

    forbidden = (
        "R_attachment",
        "o2_attachment.txt",
        "PhysicsElectronImpactAttachmentMaterial",
    )
    for token in forbidden:
        if token in text:
            raise RuntimeError(f"attachment leaked into 20 ns discriminator: {token}")

    seq = " ".join(f"{t:.17g}" for t in TIME_SEQUENCES[case])
    if f"time_sequence = '{seq}'" not in text:
        raise RuntimeError("time sequence contract mismatch")

    out = HERE / f"full_monolithic_l4_dt_ramp_ionization_20ns_{case}.i"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    print(f"case={case}; steps={EXPECTED_STEPS[case]}; end_time=20 ns")
    print("chemistry=e + O2 -> 2e + O2+ only; EI16 energy loss=12.06 eV/event")
    print("attachment=OFF; other volumetric chemistry=OFF")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=CASES, required=True)
    args = parser.parse_args()
    build(args.case)


if __name__ == "__main__":
    main()
