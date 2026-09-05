"""Quantitative D_mix equivalence analysis."""
from __future__ import annotations

from typing import Any

from qpx_harness.domains.plasma.transport import (
    DMIX_EQUIVALENCE_REL_TOL,
    OXYGEN_HEAVY_SPECIES,
)

REL_TOL = DMIX_EQUIVALENCE_REL_TOL
SPECIES = OXYGEN_HEAVY_SPECIES
TAGS = ("A", "B")


def compare(candidate: dict[str, float], legacy: dict[str, float], tol: float) -> dict[str, Any]:
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
            details.append({
                "key": key,
                "candidate": new,
                "legacy": old,
                "relative_error": rel,
            })
            if rel > tol:
                failures.append(f"{key}: {rel:.6e} > {tol:.6e}")
    return {
        "status": "PASS" if not failures else "FAIL",
        "max_relative_error": maximum,
        "relative_tolerance": tol,
        "failures": failures,
        "details": details,
    }


__all__ = ["REL_TOL", "SPECIES", "TAGS", "compare"]
