#!/usr/bin/env python3
"""Compare future Boltzmann-generated LOOKUP rates to historical formula benchmarks.

Input CSV schema: reaction_id,Te_eV,k_lookup_m3_s.
This tool only compares two physically relevant historical formula fits:
407 (Gudmundsson 2000, Maxwellian Te=1..7 eV) and
412 (Zhao 2024 empirical DISS-G fit, provenance/fit range to be audited).
NEVER use the old 4.5-eV ex1 formula to validate corrected 411 dissociation.
The comparison reports deviations, not chemical-identity or scientific PASS.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

FORMULAS = {
    407: {"citation": "Gudmundsson et al. (2000), Table 3; O2(a1Delta_g)",
          "law": "1.37e-15*exp(-2.14/Te)", "Te_range_eV": [1., 7.]},
    412: {"citation": "Zhao et al. (2024), Table I; empirical DISS-G benchmark",
          "law": "1.41e-15*Te**-0.22*exp(-2.98/Te)",
          "Te_range_eV": None},
}


def reference_k(reaction_id: int, te_eV: float) -> float:
    if reaction_id not in FORMULAS:
        raise ValueError("Formula benchmarks exist only for 407 and 412; not 411")
    if not math.isfinite(te_eV) or te_eV <= 0:
        raise ValueError("Te must be finite and positive")
    if reaction_id == 407:
        if not 1. <= te_eV <= 7.:
            raise ValueError("407 benchmark only valid for Maxwellian Te 1..7 eV")
        return 1.37e-15 * math.exp(-2.14/te_eV)
    return 1.41e-15 * te_eV ** (-0.22) * math.exp(-2.98/te_eV)


def compare(rows: list[dict[str, str]]) -> list[dict]:
    answer = []
    seen: set[tuple[int, float]] = set()
    for row in rows:
        try:
            rid = int(row["reaction_id"])
            te = float(row["Te_eV"])
            k = float(row["k_lookup_m3_s"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Require reaction_id,Te_eV,k_lookup_m3_s numeric CSV") from exc
        if rid not in FORMULAS:
            # Do not report the unrelated O2(ex1) fit as a valid 411 comparator.
            raise ValueError(f"No scientifically matched formula benchmark for {rid}")
        if (rid, te) in seen:
            raise ValueError(f"Duplicate lookup point {rid}, Te={te}")
        seen.add((rid, te))
        if not math.isfinite(k) or k < 0:
            raise ValueError("Boltzmann rate must be finite and >= 0")
        f = reference_k(rid, te)
        answer.append({
            "reaction_id": rid, "Te_eV": te, "k_lookup_m3_s": k,
            "k_formula_m3_s": f, "relative_deviation": (k-f)/f,
            "formula_reference": FORMULAS[rid]["citation"],
            "note": "comparison only; not a chemistry validity claim",
        })
    return sorted(answer, key=lambda r: (r["reaction_id"], r["Te_eV"]))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rates-csv", required=True, type=Path)
    p.add_argument("--report-json", required=True, type=Path)
    a = p.parse_args()
    with a.rates_csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("No Boltzmann rates supplied")
    results = compare(rows)
    per_id = {}
    for rid in sorted({r["reaction_id"] for r in results}):
        subset = [r for r in results if r["reaction_id"] == rid]
        per_id[str(rid)] = {
            "n": len(subset),
            "max_absolute_relative_deviation": max(abs(r["relative_deviation"]) for r in subset),
            "rms_relative_deviation": math.sqrt(
                sum(r["relative_deviation"]**2 for r in subset)/len(subset)),
        }
    report = {
        "status": "FORMULA_BENCHMARK_COMPARISON_ONLY",
        "not_physics_acceptance": True,
        "notes": ["Use same Maxwellian assumption and Te definition for 407 comparisons.",
                  "For 412, source process and empirical fit validity need separate audit.",
                  "Historical 411 ex1 formula explicitly excluded from corrected 411 dissociation."],
        "summary": per_id, "points": results,
    }
    a.report_json.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print("O2_FORMULA_BENCHMARK_COMPARISON_COMPLETE_NOT_SCIENTIFIC_PASS")
    for rid, summary in per_id.items():
        print(f"reaction={rid} points={summary['n']} max_relative_deviation={summary['max_absolute_relative_deviation']:.6g}")


if __name__ == "__main__":
    main()
