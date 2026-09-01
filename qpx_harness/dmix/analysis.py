"""Pure input/output equivalence analysis for D_mix diagnostics."""
from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Any

from .source_transform import EquivalenceError

SPECIES = ("O2", "O2s", "O2p", "O", "Om", "Op", "Os")
TAGS = ("A", "B")
REL_TOL = 2.0e-5
TRACE = {
    "w_O2": 0.99994,
    "w_O2s": 1e-5,
    "w_O2p": 1e-5,
    "w_O": 1e-5,
    "w_Om": 1e-5,
    "w_Op": 1e-5,
    "w_Os": 1e-5,
}


def quoted_values(text: str, key: str) -> tuple[re.Match[str], list[str]]:
    m = re.search(
        rf"(^\s*{re.escape(key)}\s*=\s*')([^']*)('.*$)",
        text,
        re.MULTILINE,
    )
    if not m:
        raise EquivalenceError(f"missing {key} in base input")
    return m, m.group(2).split()


def trace_input(text: str) -> str:
    _, names = quoted_values(text, "prop_names")
    values_match, values = quoted_values(text, "prop_values")
    if len(names) != len(values):
        raise EquivalenceError("prop_names/prop_values size mismatch")
    index = {name: i for i, name in enumerate(names)}
    missing = [name for name in TRACE if name not in index]
    if missing:
        raise EquivalenceError("missing trace fraction names: " + ", ".join(missing))
    for name, value in TRACE.items():
        values[index[name]] = f"{value:.12g}"
    total = sum(float(values[index[name]]) for name in TRACE)
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-14):
        raise EquivalenceError(f"trace mass fractions sum to {total}")
    replacement = values_match.group(1) + " ".join(values) + values_match.group(3)
    return text[: values_match.start()] + replacement + text[values_match.end() :]


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


def compare(
    candidate: dict[str, float], legacy: dict[str, float], tol: float
) -> dict[str, Any]:
    failures: list[str] = []
    maximum = 0.0
    details = []
    for tag in TAGS:
        for species in SPECIES:
            key = f"Dmix_{tag}_{species}"
            if key not in candidate or key not in legacy:
                failures.append(f"missing {key}")
                continue
            old = legacy[key]
            new = candidate[key]
            rel = abs(new - old) / max(abs(old), 1e-300)
            maximum = max(maximum, rel)
            details.append(
                {
                    "key": key,
                    "candidate": new,
                    "legacy": old,
                    "relative_error": rel,
                }
            )
            if rel > tol:
                failures.append(f"{key}: {rel:.6e} > {tol:.6e}")
    return {
        "status": "PASS" if not failures else "FAIL",
        "max_relative_error": maximum,
        "relative_tolerance": tol,
        "failures": failures,
        "details": details,
    }
