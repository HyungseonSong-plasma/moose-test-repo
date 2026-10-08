#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

import prepare_cases as base
import prepare_wall_layer_inward as inward

NSTEPS = 50
END_TIME = base.DT * NSTEPS


def inward_layer_case_50ns(layers: int) -> str:
    text = inward.inward_layer_case(layers)

    text, n_num = re.subn(r"  num_steps = 1\n", f"  num_steps = {NSTEPS}\n", text, count=1)
    text, n_end = re.subn(
        r"  end_time = [^\n]+\n", f"  end_time = {END_TIME:.17g}\n", text, count=1
    )
    if n_num != 1 or n_end != 1:
        raise RuntimeError("failed to extend inward wall-layer case to 50 ns")

    return text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a 50 ns hybrid case with inward-refined FV wall layers and fixed coarse-P1 potential."
    )
    parser.add_argument("--layers", type=int, choices=(2, 4), required=True)
    args = parser.parse_args()

    out = Path(base.HERE) / f"hybrid_wall_layer_L{args.layers}_coarse_p1_50ns.i"
    out.write_text(inward_layer_case_50ns(args.layers), encoding="utf-8")
    print(f"wrote {out}")
    print(f"inward topological layers={args.layers}")
    print("FV transport: selected cumulative wall layers h-refined exactly one level")
    print("FEM potential: original coarse-P1 space retained by automatic DofMap midpoint constraints")
    print(f"dt={base.DT} s; steps={NSTEPS}; end_time={END_TIME} s")


if __name__ == "__main__":
    main()
