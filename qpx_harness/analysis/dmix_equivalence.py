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


def self_test() -> int:
    try:
        baseline = {
            f"Dmix_{tag}_{species}": float(i + 1)
            for i, (tag, species) in enumerate(
                (tag, species) for tag in TAGS for species in SPECIES
            )
        }
        if compare(baseline, dict(baseline), REL_TOL)["status"] != "PASS":
            raise AssertionError("checker positive control failed")
        mutated = dict(baseline)
        mutated["Dmix_B_Op"] *= 1.1
        if compare(baseline, mutated, REL_TOL)["status"] != "FAIL":
            raise AssertionError("checker mutation was not rejected")
    except Exception as exc:
        print(f"DMIX_EQ_ANALYSIS_SELFTEST: FAIL ({exc})")
        return 1
    print("DMIX_EQ_ANALYSIS_SELFTEST: PASS")
    return 0


__all__ = ["REL_TOL", "SPECIES", "TAGS", "compare", "self_test"]
