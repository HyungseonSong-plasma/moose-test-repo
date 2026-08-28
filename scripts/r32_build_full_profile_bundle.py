#!/usr/bin/env python3
"""Legacy issue-#32 bundle CLI backed by qpx_harness.bundle."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.bundle import build_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qpx-root", required=True)
    parser.add_argument("--output", default="r32_full_profile_case.zip")
    args = parser.parse_args()

    build_bundle(
        spec_path=ROOT / "tests" / "r32_performance" / "profile_spec.json",
        qpx_root=Path(args.qpx_root),
        output=Path(args.output),
        package_root=ROOT,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
