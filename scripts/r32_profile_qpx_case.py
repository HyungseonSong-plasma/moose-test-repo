#!/usr/bin/env python3
"""Legacy issue-#32 profiling CLI backed by qpx_harness.profiling."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.profiling import profile_case


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--qpx")
    parser.add_argument("--out-dir")
    args = parser.parse_args()

    return profile_case(
        case_dir=Path(args.case_dir),
        input_name=args.input,
        label=args.label,
        executable=args.qpx,
        out_dir=Path(args.out_dir) if args.out_dir else None,
        issue=32,
        prefix="r32",
        output_namespace="r32_profiles",
        num_steps=1,
    )


if __name__ == "__main__":
    raise SystemExit(main())
