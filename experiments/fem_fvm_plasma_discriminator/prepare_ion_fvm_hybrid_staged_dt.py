#!/usr/bin/env python3
from pathlib import Path
import prepare_cases as base
import prepare_ion_fvm_hybrid_contour as hybrid


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}, found {count}")
    return text.replace(old, new, 1)


def time_sequence(second_dt: float, second_steps: int):
    # 0 -> 100 ns: 1 ns x 100, then continue with the requested larger fixed dt.
    first = [i * base.DT for i in range(base.NSTEPS + 1)]
    t0 = base.NSTEPS * base.DT
    second = [t0 + j * second_dt for j in range(1, second_steps + 1)]
    return first + second


def build_staged_case(second_dt: float, second_steps: int) -> str:
    text = hybrid.build_case()

    old_time = f"""  dt = {base.DT:.17g}\n  num_steps = {hybrid.HYBRID_NSTEPS}\n  end_time = {hybrid.HYBRID_END_TIME:.17g}\n"""

    seq = time_sequence(second_dt, second_steps)
    seq_string = " ".join(f"{t:.17g}" for t in seq)
    new_time = f"""  end_time = {seq[-1]:.17g}\n  [TimeStepper]\n    type = TimeSequenceStepper\n    time_sequence = '{seq_string}'\n  []\n"""
    text = replace_once(text, old_time, new_time, "fixed time settings")
    return text


def write_case(name: str, second_dt: float, second_steps: int):
    out = Path(base.HERE) / f"{name}.i"
    out.write_text(build_staged_case(second_dt, second_steps), encoding="utf-8")
    seq = time_sequence(second_dt, second_steps)
    print(f"wrote {out}")
    print(f"schedule: 1 ns x {base.NSTEPS} + {second_dt*1e9:g} ns x {second_steps}")
    print(f"total steps={len(seq)-1}; end_time={seq[-1]*1e9:g} ns")


if __name__ == "__main__":
    write_case("ion_fvm_hybrid_staged_1ns100_5ns100", 5.0e-9, 100)
    write_case("ion_fvm_hybrid_staged_1ns100_10ns50", 10.0e-9, 50)
