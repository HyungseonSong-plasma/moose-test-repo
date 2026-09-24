"""Issue #310 Gen16 combined evidence aggregation."""
from __future__ import annotations
import argparse, json, os
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results_fp16_combined"
RELAX_CASES = (
    "picard2x_control",
    "band5_alpha002",
    "band5_alpha005",
    "band5_alpha010",
    "band5_alpha020",
)

def aggregate() -> dict[str, object]:
    root_raw = os.environ.get("CHATGPT_MATRIX_EVIDENCE_ROOT")
    if not root_raw:
        raise SystemExit("CHATGPT_MATRIX_EVIDENCE_ROOT is required")
    root = Path(root_raw)
    state_files = list(root.rglob("state_jacobian_summary.json"))
    state = json.loads(state_files[0].read_text(encoding="utf-8")) if len(state_files) == 1 else None

    found = {}
    for path in root.rglob("*_result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        name = str(item.get("case", ""))
        if name in RELAX_CASES:
            found[name] = item

    control = found.get("picard2x_control")
    trials = {}
    if control:
        cfp = control.get("cumulative_fixed_point_iterations")
        for name in RELAX_CASES[1:]:
            item = found.get(name)
            if not item:
                continue
            fp = item.get("cumulative_fixed_point_iterations")
            row = {
                "outer_relaxation_factor": item.get("outer_relaxation_factor"),
                "classification": item.get("classification"),
                "evidence_valid": bool(item.get("evidence_valid")),
                "cumulative_fixed_point_iterations": fp,
                "average_fixed_point_iterations_per_observed_step":
                    item.get("average_fixed_point_iterations_per_observed_step"),
            }
            if isinstance(fp, (int,float)) and isinstance(cfp, (int,float)) and cfp:
                row["fixed_point_reduction_fraction_vs_control"] = 1.0 - float(fp)/float(cfp)
            trials[name] = row

    valid = [
        (name, row["cumulative_fixed_point_iterations"])
        for name, row in trials.items()
        if row.get("evidence_valid") and isinstance(row.get("cumulative_fixed_point_iterations"), (int,float))
    ]
    best = min(valid, key=lambda x: x[1]) if valid else None
    missing_relax = [x for x in RELAX_CASES if x not in found]

    out = {
        "issue": 310,
        "sequence": 16,
        "classification": (
            "GEN16_COMBINED_EVIDENCE_COMPLETE"
            if state is not None and not missing_relax
            else "GEN16_COMBINED_EVIDENCE_PARTIAL"
        ),
        "state_jacobian": state,
        "relaxation_control": control,
        "relaxation_trials": trials,
        "best_valid_relaxation_case": (
            {"case": best[0], "cumulative_fixed_point_iterations": best[1]} if best else None
        ),
        "missing_relaxation_cases": missing_relax,
        "state_jacobian_missing": state is None,
        "guard": (
            "The state-Jacobian lane diagnoses operating-point dependence; the relaxation lane "
            "changes only the outer Picard relaxation while retaining the Gen15 band-5 operator. "
            "No production promotion is implied by short-horizon completion alone."
        ),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "issue310_gen16_combined_summary.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return out

def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--aggregate", action="store_true")
    args=ap.parse_args()
    if not args.aggregate:
        ap.error("--aggregate required")
    out=aggregate()
    print("ISSUE310_GEN16_COMBINED:", out["classification"])

if __name__ == "__main__":
    main()
