#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

import prepare_cases as base
import prepare_wall_layer_inward as inward

TARGET_END_TIME = 50.0e-9
MAX_STEPS = 100


def inward_layer_case_50ns(layers: int) -> str:
    text = inward.inward_layer_case(layers)

    # end_time, not successful-step count, is the physical stopping criterion.
    # Keep a generous step cap so nonlinear timestep cutbacks do not terminate
    # the run before 50 ns.
    text, n_num = re.subn(r"  num_steps = 1\n", f"  num_steps = {MAX_STEPS}\n", text, count=1)
    text, n_end = re.subn(
        r"  end_time = [^\n]+\n", f"  end_time = {TARGET_END_TIME:.17g}\n", text, count=1
    )
    if n_num != 1 or n_end != 1:
        raise RuntimeError("failed to extend inward wall-layer case to a true 50 ns end time")

    return text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a true 50 ns hybrid case with inward-refined FV wall layers and fixed coarse-P1 potential."
    )
    parser.add_argument("--layers", type=int, choices=(2, 4), required=True)
    args = parser.parse_args()

    out = Path(base.HERE) / f"hybrid_wall_layer_L{args.layers}_coarse_p1_50ns.i"
    out.write_text(inward_layer_case_50ns(args.layers), encoding="utf-8")
    print(f"wrote {out}")
    print(f"inward topological layers={args.layers}")
    print("FV transport: selected cumulative wall layers h-refined exactly one level")
    print("FEM potential: original coarse-P1 space retained by automatic DofMap midpoint constraints")
    print(f"initial dt={base.DT} s; max_steps={MAX_STEPS}; target end_time={TARGET_END_TIME} s")


if __name__ == "__main__":
    main()
