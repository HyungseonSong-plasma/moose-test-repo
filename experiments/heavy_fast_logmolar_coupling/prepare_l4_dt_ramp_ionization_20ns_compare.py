#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import prepare_l4_o2_ionization_ab as chem
import prepare_l4_dt_compare as core

HERE = Path(__file__).resolve().parent
NA = 6.02214076e23
TARGET_NE = 1.0e15
TOTAL_TIME = 2.0e-8

# All three cases use the same timestep ramp:
#   0 -> 10 ns : 0.1 ns x 100
#   10 -> 20 ns: 0.2 ns x 50
#
# reference reproduces the pre-ion-temperature wall model and the historical
# initial electron mean energy.  The 2 eV and 4 eV cases match Ti and Te at
# startup; for a Maxwellian electron population <epsilon_e> = 3/2 Te.
CASE_CONFIG = {
    "reference": {
        "ion_temperature_eV": 0.0,
        "electron_temperature_eV": None,
        "mean_energy_eV": 5.73276,
    },
    "ti_te_2eV": {
        "ion_temperature_eV": 2.0,
        "electron_temperature_eV": 2.0,
        "mean_energy_eV": 3.0,
    },
    "ti_te_4eV": {
        "ion_temperature_eV": 4.0,
        "electron_temperature_eV": 4.0,
        "mean_energy_eV": 6.0,
    },
}
CASES = tuple(CASE_CONFIG)


def _ramp_times() -> tuple[float, ...]:
    first = [i * 1.0e-10 for i in range(101)]
    second = [1.0e-8 + j * 2.0e-10 for j in range(1, 51)]
    return tuple(first + second)


RAMP_TIMES = _ramp_times()
EXPECTED_STEPS = 150


def _set_time_ramp(text: str) -> str:
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

    if len(RAMP_TIMES) - 1 != EXPECTED_STEPS:
        raise RuntimeError("unexpected number of ramp steps")
    if abs(RAMP_TIMES[-1] - TOTAL_TIME) > 1.0e-20:
        raise RuntimeError("time ramp does not end at 20 ns")

    seq = " ".join(f"{t:.17g}" for t in RAMP_TIMES)
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


def _set_ion_temperature(text: str, temperature_eV: float) -> str:
    for material in (
        "O2p_wall_flux_feedback",
        "Op_wall_flux_monolithic",
        "Om_wall_flux_monolithic",
    ):
        text = core.set_child_parameter(
            text,
            material,
            "ion_temperature_eV",
            f"{temperature_eV:.1f}",
        )
    return text


def _set_initial_mean_energy(text: str, mean_energy_eV: float) -> str:
    log_energy_initial = math.log((TARGET_NE / NA) * mean_energy_eV)
    return core.set_child_parameter(
        text,
        "log_energy",
        "initial_condition",
        f"{log_energy_initial:.17g}",
    )


def build(case: str) -> Path:
    if case not in CASES:
        raise ValueError(case)

    cfg = CASE_CONFIG[case]

    # Same physics as the successful O2-ionization-only monolithic case:
    # ne=nO2+=1e15 m^-3, pure O2 20 sccm, 10 mTorr, ionization only.
    baseline = chem.build("o2_ionization_on")
    text = baseline.read_text(encoding="utf-8")

    # Override inherited startup energy explicitly so the reference remains the
    # historical pre-temperature-test value even though the common feedback
    # generator now defaults to Te=4 eV / <epsilon>=6 eV.
    text = _set_initial_mean_energy(text, cfg["mean_energy_eV"])
    text = _set_ion_temperature(text, cfg["ion_temperature_eV"])
    text = _set_time_ramp(text)

    required = (
        "type = PhysicsElectronImpactIonizationMaterial",
        "rate_table_file = ../../physics_app/data/electron_impact/o2_ionization.txt",
        "type = PhysicsO2IonizationSourceMaterial",
        "type = PhysicsFVLogMolarElectronReactionSource",
        "number_source = electron_ionization_number_source",
        "source = O2p_ionization_mass_source",
        "v = R_ion_O2",
        "coef = -12.06",
        f"ion_temperature_eV = {cfg['ion_temperature_eV']:.1f}",
        "type = TimeSequenceStepper",
        f"end_time = {TOTAL_TIME:.17g}",
    )
    for token in required:
        if token not in text:
            raise RuntimeError(f"20 ns temperature-ramp case missing required token: {token}")

    expected_log_energy = math.log((TARGET_NE / NA) * cfg["mean_energy_eV"])
    log_energy_block = core.child_block(text, "log_energy")
    if f"    initial_condition = {expected_log_energy:.17g}" not in log_energy_block:
        raise RuntimeError("electron startup mean-energy contract mismatch")

    forbidden = (
        "R_attachment",
        "o2_attachment.txt",
        "PhysicsElectronImpactAttachmentMaterial",
    )
    for token in forbidden:
        if token in text:
            raise RuntimeError(f"attachment leaked into 20 ns temperature-ramp case: {token}")

    seq = " ".join(f"{t:.17g}" for t in RAMP_TIMES)
    if f"time_sequence = '{seq}'" not in text:
        raise RuntimeError("time-ramp contract mismatch")

    out = HERE / f"full_monolithic_l4_dt_ramp_ionization_20ns_{case}.i"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    print(f"case={case}; steps={EXPECTED_STEPS}; end_time=20 ns")
    print("ramp=0.1 ns x100 then 0.2 ns x50")
    print("chemistry=e + O2 -> 2e + O2+ only; EI16 energy loss=12.06 eV/event")
    if cfg["electron_temperature_eV"] is None:
        print(
            "reference: ion wall thermal velocity uses gas_temperature; "
            f"initial electron mean energy={cfg['mean_energy_eV']:.5f} eV"
        )
    else:
        print(
            f"Ti={cfg['ion_temperature_eV']:.1f} eV; "
            f"Te={cfg['electron_temperature_eV']:.1f} eV; "
            f"initial electron mean energy={cfg['mean_energy_eV']:.1f} eV"
        )
    print("attachment=OFF; other volumetric chemistry=OFF")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=CASES, required=True)
    args = parser.parse_args()
    build(args.case)


if __name__ == "__main__":
    main()
