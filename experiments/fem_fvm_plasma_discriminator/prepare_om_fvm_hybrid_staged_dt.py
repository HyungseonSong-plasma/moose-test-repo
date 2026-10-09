#!/usr/bin/env python3
"""Build the Issue #378 O- case with a 100 us staged time grid.

Schedule:
  0 -> 100 ns    : 1 ns x 100
  100 ns -> 1 us : 10 ns x 90
  1 us -> 10 us  : 100 ns x 90
  10 us -> 100 us: 1000 ns x 90
"""
from pathlib import Path

import prepare_cases as base
import prepare_ion_fvm_hybrid_contour as hybrid
import prepare_om_fvm_hybrid_contour as om

FIRST_DT = 1.0e-9
FIRST_STEPS = 100
SECOND_DT = 10.0e-9
SECOND_STEPS = 90
THIRD_DT = 100.0e-9
THIRD_STEPS = 90
FOURTH_DT = 1000.0e-9
FOURTH_STEPS = 90
CASE_NAME = "ion_om_fvm_hybrid_contour_staged_1ns100_10ns90_100ns90_1000ns90"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def time_sequence() -> list[float]:
    first = [i * FIRST_DT for i in range(FIRST_STEPS + 1)]
    t1 = FIRST_STEPS * FIRST_DT
    second = [t1 + j * SECOND_DT for j in range(1, SECOND_STEPS + 1)]
    t2 = t1 + SECOND_STEPS * SECOND_DT
    third = [t2 + k * THIRD_DT for k in range(1, THIRD_STEPS + 1)]
    t3 = t2 + THIRD_STEPS * THIRD_DT
    fourth = [t3 + m * FOURTH_DT for m in range(1, FOURTH_STEPS + 1)]
    seq = first + second + third + fourth
    if len(seq) != FIRST_STEPS + SECOND_STEPS + THIRD_STEPS + FOURTH_STEPS + 1:
        raise RuntimeError("staged time sequence length changed")
    if abs(seq[-1] - 100.0e-6) > 1.0e-15:
        raise RuntimeError(f"staged end time changed: {seq[-1]:.17g}")
    return seq


def build_case() -> str:
    text = om.build_case()

    old_time = f"""  dt = {base.DT:.17g}\n  num_steps = {hybrid.HYBRID_NSTEPS}\n  end_time = {hybrid.HYBRID_END_TIME:.17g}\n"""

    seq = time_sequence()
    seq_string = " ".join(f"{t:.17g}" for t in seq)
    new_time = f"""  end_time = {seq[-1]:.17g}\n  [TimeStepper]\n    type = TimeSequenceStepper\n    time_sequence = '{seq_string}'\n  []\n"""
    text = replace_once(text, old_time, new_time, "300 ns fixed time settings")

    if "type = TimeSequenceStepper" not in text:
        raise RuntimeError("missing staged TimeSequenceStepper")
    if "[log_nm]" not in text or "charge_number = -1" not in text:
        raise RuntimeError("O- transport contract was lost while staging dt")

    return text


def main() -> None:
    seq = time_sequence()
    switch2 = FIRST_STEPS + SECOND_STEPS
    switch3 = switch2 + THIRD_STEPS
    out = Path(base.HERE) / f"{CASE_NAME}.i"
    out.write_text(build_case(), encoding="utf-8")
    print(f"wrote {out}")
    print("schedule: 1 ns x 100 + 10 ns x 90 + 100 ns x 90 + 1000 ns x 90")
    print(f"total_steps={len(seq)-1}")
    print(f"states={len(seq)}")
    print(f"switch1_time_ns={seq[FIRST_STEPS] * 1.0e9:.17g}")
    print(f"switch2_time_us={seq[switch2] * 1.0e6:.17g}")
    print(f"switch3_time_us={seq[switch3] * 1.0e6:.17g}")
    print(f"end_time_us={seq[-1] * 1.0e6:.17g}")


if __name__ == "__main__":
    main()
