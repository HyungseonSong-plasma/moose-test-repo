#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recipes.issue91_r3 import build_r3_input


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--field", type=float, required=True)
    args = parser.parse_args()
    base = Path("heavy_base.i").read_text()
    text, meta = build_r3_input(base, field_strength=args.field)
    Path("input.i").write_text(text)
    Path("prepare_evidence.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    print("ISSUE91_R3_PREPARE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
