#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPT = ROOT / "scripts" / "r32_analyze_profile.py"
FIXTURE = HERE / "evr1_t2_heavy.json"


def load_module():
    spec = importlib.util.spec_from_file_location("r32_analyze_profile", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_module()
    fixture = json.loads(FIXTURE.read_text())

    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        summary = tmp / "summary.json"
        petsc = tmp / "petsc.csv"
        perf = tmp / "p3_run.log"

        summary.write_text(
            json.dumps(
                {
                    "issue": 32,
                    "label": "T2-heavy",
                    "p2_returncode": 0,
                    "p3_returncode": 0,
                    "wall_seconds": fixture["wall_seconds"],
                    "last_metrics_row": {
                        "time": str(fixture["metrics"]["time"]),
                        "r32_num_dofs": str(fixture["metrics"]["dofs"]),
                        "r32_nonlinear_iterations": str(fixture["metrics"]["nonlinear_iterations"]),
                        "r32_linear_iterations": str(fixture["metrics"]["linear_iterations"]),
                        "r32_residual_evaluations": str(fixture["metrics"]["residual_evaluations"]),
                    },
                }
            )
        )

        fields = ["Stage Name", "Event Name", "Rank", "Count", "Time"]
        rows = [
            ("SNESSolve", 1, "snes_solve"),
            ("SNESJacobianEval", 3, "jacobian_eval"),
            ("SNESFunctionEval", 4, "residual_eval"),
            ("PCSetUp", 3, "pc_setup"),
            ("MatLUFactorNum", 3, "lu_numeric"),
            ("MatLUFactorSym", 1, "lu_symbolic"),
            ("KSPSolve", 3, "linear_solve"),
            ("MatAssemblyEnd", 9, "matrix_assembly_end"),
        ]
        with petsc.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for event, count, key in rows:
                writer.writerow(
                    {
                        "Stage Name": "Main Stage",
                        "Event Name": event,
                        "Rank": "0",
                        "Count": count,
                        "Time": fixture["petsc_seconds"][key],
                    }
                )

        pj = fixture["perfgraph_jacobian_self"]
        perf.write_text(
            "Heaviest Sections:\n"
            f"| NonlinearSystemBase::computeJacobianInternal | {pj['calls']} | "
            f"{pj['self_seconds']:.3f} | {pj['avg_seconds']:.3f} | "
            f"{pj['percent_application']:.2f} | 51 |\n"
        )

        result = module.analyze(summary, petsc, perf)

    assert result["classification"] == fixture["classification"], result
    assert "DIRECT_FACTORIZATION_SIGNIFICANT" in result["secondary"], result
    assert "RESIDUAL_EVALUATION_SIGNIFICANT" in result["secondary"], result
    assert result["dofs"] == 21132, result
    assert abs(result["petsc_seconds"]["jacobian_eval"] - 12.1323) < 1e-9, result
    assert result["perfgraph_jacobian_self"]["calls"] == 4, result
    print("R32_ANALYZER_SELFTEST PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
