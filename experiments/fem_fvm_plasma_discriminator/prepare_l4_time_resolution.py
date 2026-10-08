#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

import prepare_cases as base
import prepare_wall_layer_inward as inward

END_TIME = 40.0e-9


def uniform_times(dt_ns: float, steps: int):
    return [i * dt_ns * 1.0e-9 for i in range(steps + 1)]


def mixed_times():
    # 0.2 ns x 100 -> 20 ns, then 0.4 ns x 50 -> 40 ns.
    times = uniform_times(0.2, 100)
    start = times[-1]
    times.extend(start + i * 0.4e-9 for i in range(1, 51))
    return times


CASES = {
    "dt02_then_04": {
        "times": mixed_times(),
        "label": "0.2 ns x 100 + 0.4 ns x 50",
    },
    "dt04": {
        "times": uniform_times(0.4, 100),
        "label": "0.4 ns x 100",
    },
    "dt08": {
        "times": uniform_times(0.8, 50),
        "label": "0.8 ns x 50",
    },
}


def build_case(case_id: str) -> str:
    spec = CASES[case_id]
    times = spec["times"]
    if abs(times[-1] - END_TIME) > 1e-18:
        raise RuntimeError(f"{case_id}: final time is not 40 ns: {times[-1]}")

    # Start from the already validated L4 hybrid spatial discretization.
    text = inward.inward_layer_case(4)

    # TimeSequenceStepper owns the timestep grid, so remove inherited scalar dt.
    text, n_dt = re.subn(r"  dt = [^\n]+\n", "", text, count=1)
    text, n_num = re.subn(r"  num_steps = 1\n", "  num_steps = 400\n", text, count=1)
    text, n_end = re.subn(
        r"  end_time = [^\n]+\n", f"  end_time = {END_TIME:.17g}\n", text, count=1
    )
    if n_dt != 1 or n_num != 1 or n_end != 1:
        raise RuntimeError("failed to replace inherited time-stepping controls")

    sequence = " ".join(f"{t:.17g}" for t in times)
    anchor = f"  end_time = {END_TIME:.17g}\n"
    block = (
        anchor
        + "  [TimeStepper]\n"
        + "    type = TimeSequenceStepper\n"
        + f"    time_sequence = '{sequence}'\n"
        + "  []\n"
    )
    if text.count(anchor) != 1:
        raise RuntimeError("expected exactly one end_time anchor")
    text = text.replace(anchor, block, 1)
    return text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build L4 fixed-space temporal-resolution discriminator cases to 40 ns."
    )
    parser.add_argument("--case", choices=tuple(CASES), required=True)
    args = parser.parse_args()

    spec = CASES[args.case]
    out = Path(base.HERE) / f"hybrid_L4_time_{args.case}.i"
    out.write_text(build_case(args.case), encoding="utf-8")

    times = spec["times"]
    dts_ns = [(times[i + 1] - times[i]) * 1e9 for i in range(len(times) - 1)]
    print(f"wrote {out}")
    print("spatial discretization: L4 fixed")
    print(f"time schedule: {spec['label']}")
    print(f"scheduled steps={len(times)-1}; end_time={times[-1]*1e9:.12g} ns")
    print(f"dt range={min(dts_ns):.12g}..{max(dts_ns):.12g} ns")


if __name__ == "__main__":
    main()
