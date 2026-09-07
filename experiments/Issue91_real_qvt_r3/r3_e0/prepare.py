#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
ROOT = CASE_DIR.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.historical_recipe_support.issue91_r3 import build_r3_input


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--field", type=float, required=True)
    args = parser.parse_args()
    base = (CASE_DIR / "heavy_base.i").read_text()
    text, meta = build_r3_input(base, field_strength=args.field)
    (CASE_DIR / "input.i").write_text(text)
    (CASE_DIR / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n"
    )
    print("ISSUE91_R3_PREPARE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
