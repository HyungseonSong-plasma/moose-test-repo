#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path

CASE = Path(__file__).resolve().parent
OUT = CASE / "results_outer"
FACTORS = (1, 2, 4, 8, 16, 32)
PROBES = (
    "E_imag_probe_r05",
    "E_imag_probe_r10",
    "E_imag_probe_r15",
    "E_imag_probe_r20",
    "E_imag_probe_upper_r05",
    "E_imag_probe_upper_r12",
    "E_imag_probe_upper_r18",
)
TAIL_MAX_REL = 0.005
REFINEMENT_MAX_REL = 0.01


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def final_row(case: str) -> dict[str, float]:
    path = OUT / f"{case}.csv"
    if not path.is_file():
        fail(f"missing CSV output: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        fail(f"empty CSV output: {path}")
    out: dict[str, float] = {}
    for key, value in rows[-1].items():
        if key is None or value is None or not value.strip():
            continue
        try:
            out[key] = float(value)
        except ValueError:
            pass
    return out


def rel_change(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1.0)


def main() -> None:
    manifest_path = OUT / "outer_domain_manifest.json"
    if not manifest_path.is_file():
        fail(f"missing outer-domain manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = {factor: final_row(f"outer_{factor}") for factor in FACTORS}
    refined32 = final_row("outer_32_refined")

    required = ("E_real_l2", "E_imag_l2", "E_imag_min", "E_imag_max", *PROBES)
    for name, row in [(f"outer_{f}", rows[f]) for f in FACTORS] + [("outer_32_refined", refined32)]:
        missing = [key for key in required if key not in row]
        if missing:
            fail(f"{name}: missing observables {missing}")
        if abs(row["E_real_l2"]) > 1e-12:
            fail(f"{name}: E_real_l2 must remain zero, got {row['E_real_l2']}")

    comparisons: dict[str, dict[str, float]] = {}
    for a, b in zip(FACTORS[:-1], FACTORS[1:]):
        comparisons[f"factor{a}_vs_factor{b}"] = {key: rel_change(rows[a][key], rows[b][key]) for key in PROBES}
    comparisons["factor1_vs_factor32"] = {key: rel_change(rows[1][key], rows[32][key]) for key in PROBES}
    refinement = {key: rel_change(rows[32][key], refined32[key]) for key in PROBES}

    max_tail = max(comparisons["factor16_vs_factor32"].values())
    max_refine = max(refinement.values())
    max_baseline = max(comparisons["factor1_vs_factor32"].values())
    converged = max_tail < TAIL_MAX_REL
    stretch_resolved = max_refine < REFINEMENT_MAX_REL

    summary = {
        "issue": 202,
        "scope": "M2-F zero-E_theta outer-domain sensitivity extended through factor 32",
        "status": "PASS" if converged and stretch_resolved else "FAIL",
        "scientific_acceptance": False,
        "classification": (
            "FINITE_DIRICHLET_TAIL_CONVERGED" if converged else "FINITE_DIRICHLET_TAIL_NOT_CONVERGED"
        ),
        "criteria": {
            "factor16_vs_factor32_max_relative": TAIL_MAX_REL,
            "factor32_coarse_vs_refined_max_relative": REFINEMENT_MAX_REL,
        },
        "max_relative_changes": {
            "factor1_vs_factor32": max_baseline,
            "factor16_vs_factor32": max_tail,
            "factor32_coarse_vs_refined": max_refine,
        },
        "probe_relative_changes": comparisons,
        "factor32_mesh_resolution_check": refinement,
        "fields": {str(f): {key: rows[f][key] for key in required} for f in FACTORS},
        "factor32_refined_fields": {key: refined32[key] for key in required},
        "domain_manifest": manifest,
        "notes": [
            "Global E_imag_l2 is diagnostic only because the integration domain changes.",
            "Fixed internal signed probes determine outer-domain sensitivity.",
            "The factor-32 uniform-refinement cross-check separates stretched-buffer discretization from boundary-location effects.",
        ],
    }
    (OUT / "outer_domain_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not stretch_resolved:
        fail(f"factor-32 stretched-buffer mesh is under-resolved: coarse/refined max relative change={max_refine:.6g}")
    if not converged:
        fail(f"zero-E_theta finite outer boundary is still not converged by factor 32: factor16->32 max relative change={max_tail:.6g}")
    print("PASS: Issue #202 M2-F outer-domain sensitivity discriminator")


if __name__ == "__main__":
    main()
