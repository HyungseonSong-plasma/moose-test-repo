"""Observation of D_mix values from QPX CSV output."""
from __future__ import annotations

import csv
import math
from pathlib import Path

from qpx_harness.analysis.dmix_equivalence import SPECIES, TAGS
from qpx_harness.adapters.moose.dmix_equivalence import EquivalenceError


def read_dmix(csv_path: Path) -> dict[str, float]:
    if not csv_path.is_file():
        raise EquivalenceError(f"missing output {csv_path}")
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise EquivalenceError(f"no rows in {csv_path}")
    row = rows[-1]
    out: dict[str, float] = {}
    for tag in TAGS:
        for species in SPECIES:
            key = f"Dmix_{tag}_{species}"
            try:
                value = float(row[key])
            except (KeyError, ValueError) as exc:
                raise EquivalenceError(f"bad {key}: {exc}") from exc
            if not math.isfinite(value) or value <= 0:
                raise EquivalenceError(f"non-positive/non-finite {key}={value}")
            out[key] = value
    return out


__all__ = ["read_dmix"]
