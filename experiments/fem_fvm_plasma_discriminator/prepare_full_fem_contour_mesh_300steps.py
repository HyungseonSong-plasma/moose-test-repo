#!/usr/bin/env python3
from pathlib import Path
import re

import prepare_full_fem_contour_mesh as base_case


def replace_once_regex(text: str, pattern: str, repl: str, label: str) -> str:
    new_text, count = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label}, found {count}")
    return new_text


def build_case() -> str:
    text = base_case.build_case()
    text = replace_once_regex(text, r"^  num_steps = 100$", "  num_steps = 300", "num_steps")
    text = replace_once_regex(text, r"^  end_time = .*?$", "  end_time = 3e-07", "end_time")
    return text


if __name__ == "__main__":
    out = Path(base_case.base.HERE) / "full_fem_contour_mesh_dt1ns_300steps.i"
    out.write_text(build_case(), encoding="utf-8")
    print(f"wrote {out}")
    print("mesh: same accepted 3-level contour mesh")
    print("L1 h=22 mm; L2 h=11 mm; L3/boundary h=4.5 mm")
    print("L3 thickness=15.5 mm; L2 thickness=19 mm")
    print("electron particle wall BC: thermal-only")
    print("electron energy wall BC: thermal-only")
    print("dt=1e-9 s; steps=300; end_time=3e-7 s = 300 ns")
