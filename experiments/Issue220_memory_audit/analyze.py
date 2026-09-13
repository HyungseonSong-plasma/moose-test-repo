#!/usr/bin/env python3
"""Issue #220 M1: attribute W5 EVR-2 resident-memory scaling from governed logs.

This diagnostic consumes the existing governed Issue-216 EVR-2 artifact instead
of repeating the known ~15.4-GB direct-LU R2 path. It does not execute Physics or
change production/numerical semantics.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

from physics_harness.adapters.moose.performance.collection import parse_problem_identity
from physics_harness.adapters.moose.performance.profile import resident_memory_profile

CASE_LOGS = {
    "R0": "coarse_runtime.log",
    "R1": "refine_1_runtime.log",
    "R2": "refine_2_runtime.log",
}
EXPECTED_SOURCE_RUN_ID = 34723732242
EXPECTED_SOURCE_HEAD = "39ca8b09317095f58b61df84c9fb3f40b4ff0ddc"
EXPECTED_ARTIFACT_DIGEST = (
    "sha256:22f855f72b4e0f1255dab566c699b6c9952de0cccd0addba23814ee77230b592"
)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class Issue220Error(RuntimeError):
    pass


def _clean(path: Path) -> str:
    return _ANSI_RE.sub("", path.read_text(errors="replace"))


def _solver_identity(text: str) -> dict[str, str | None]:
    def value(pattern: str) -> str | None:
        match = re.search(pattern, text, re.MULTILINE)
        return match.group(1).strip() if match else None

    return {
        "petsc_preconditioner": value(r"^\s*PETSc Preconditioner:\s*(.+?)\s*$"),
        "moose_preconditioner": value(r"^\s*MOOSE Preconditioner:\s*(.+?)\s*$"),
        "solver_mode": value(r"^\s*Solver Mode:\s*(.+?)\s*$"),
    }


def _sample_mb(sample: Mapping[str, Any] | None) -> float | None:
    if not sample:
        return None
    value = sample.get("resident_mb")
    return float(value) if isinstance(value, (int, float)) else None


def _ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0.0:
        return None
    return a / b


def _case_summary(level: str, log_path: Path) -> dict[str, Any]:
    if not log_path.is_file():
        raise Issue220Error(f"missing governed runtime log: {log_path}")
    text = _clean(log_path)
    problem = parse_problem_identity(text)
    memory = resident_memory_profile(log_path)
    first_linear = memory.get("first_linear_solve") or {}
    before = first_linear.get("before")
    after = first_linear.get("after")
    peak = memory.get("peak")
    setup = memory.get("initial_setup")
    user_objects = memory.get("user_objects")
    dofs = problem.get("dofs")
    peak_mb = _sample_mb(peak)
    pre_mb = _sample_mb(before)
    post_mb = _sample_mb(after)
    setup_mb = _sample_mb(setup)
    first_mb = _sample_mb(memory.get("first_sample"))
    linear_increment = (
        post_mb - pre_mb if post_mb is not None and pre_mb is not None else None
    )
    assembly_increment = (
        pre_mb - setup_mb if pre_mb is not None and setup_mb is not None else None
    )
    return {
        "level": level,
        "log": str(log_path),
        "problem": problem,
        "solver": _solver_identity(text),
        "memory": {
            "first_sample_mb": first_mb,
            "user_objects_mb": _sample_mb(user_objects),
            "initial_setup_mb": setup_mb,
            "pre_first_linear_mb": pre_mb,
            "post_first_linear_mb": post_mb,
            "first_linear_increment_mb": linear_increment,
            "first_linear_after_before_ratio": first_linear.get("ratio_after_before"),
            "assembly_increment_after_setup_mb": assembly_increment,
            "peak_resident_mb": peak_mb,
            "peak_mb_per_million_dofs": (
                peak_mb / (float(dofs) / 1.0e6)
                if peak_mb is not None and isinstance(dofs, int) and dofs > 0
                else None
            ),
            "first_linear_increment_fraction_of_peak": (
                linear_increment / peak_mb
                if linear_increment is not None and peak_mb not in (None, 0.0)
                else None
            ),
            "samples_observed": len(memory.get("samples", [])),
            "linear_solves_observed": len(memory.get("linear_solve_transitions", [])),
        },
    }


def _cross_level(cases: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    r1 = cases["R1"]
    r2 = cases["R2"]
    m1 = r1["memory"]
    m2 = r2["memory"]
    p1 = r1["problem"]
    p2 = r2["problem"]
    dof_ratio = _ratio(
        float(p2["dofs"]) if p2.get("dofs") is not None else None,
        float(p1["dofs"]) if p1.get("dofs") is not None else None,
    )
    return {
        "r2_over_r1_dof_ratio": dof_ratio,
        "r2_over_r1_pre_linear_memory_ratio": _ratio(
            m2.get("pre_first_linear_mb"), m1.get("pre_first_linear_mb")
        ),
        "r2_over_r1_first_linear_increment_ratio": _ratio(
            m2.get("first_linear_increment_mb"), m1.get("first_linear_increment_mb")
        ),
        "r2_over_r1_peak_memory_ratio": _ratio(
            m2.get("peak_resident_mb"), m1.get("peak_resident_mb")
        ),
    }


def _decision(cases: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    r1 = cases["R1"]
    r2 = cases["R2"]
    m1 = r1["memory"]
    m2 = r2["memory"]
    solver_direct_lu = (
        r1["solver"].get("petsc_preconditioner") == "lu"
        and r2["solver"].get("petsc_preconditioner") == "lu"
    )
    r1_pre = m1.get("pre_first_linear_mb")
    r1_inc = m1.get("first_linear_increment_mb")
    r2_pre = m2.get("pre_first_linear_mb")
    r2_inc = m2.get("first_linear_increment_mb")
    attribution_ready = all(
        isinstance(value, (int, float))
        for value in (r1_pre, r1_inc, r2_pre, r2_inc)
    )
    linear_dominates = bool(
        attribution_ready
        and float(r1_inc) > float(r1_pre)
        and float(r2_inc) > float(r2_pre)
    )
    baseline_scaling = bool(
        attribution_ready and float(r2_pre) > float(r1_pre)
    )

    if attribution_ready and solver_direct_lu and linear_dominates:
        dominant_class = "DIRECT_LU_FIRST_LINEAR_SOLVE_AMPLIFICATION"
        status = "ISSUE220_M1_ATTRIBUTION_READY"
    elif attribution_ready and linear_dominates:
        dominant_class = "FIRST_LINEAR_SOLVE_AMPLIFICATION"
        status = "ISSUE220_M1_ATTRIBUTION_READY"
    else:
        dominant_class = "UNRESOLVED"
        status = "ISSUE220_M1_ATTRIBUTION_HOLD"

    return {
        "status": status,
        "dominant_owner_class": dominant_class,
        "baseline_scaling_is_nontrivial": baseline_scaling,
        "direct_lu_identity_confirmed": solver_direct_lu,
        "attribution_basis": (
            "nearest live resident-memory samples immediately before and after "
            "the first reported linear solve on R1 and R2"
        ),
        "interpretation_boundary": (
            "The first-linear-solve increment is resident-memory growth across "
            "that event. With PETSc preconditioner=lu it strongly implicates "
            "direct factorization/PC setup as the dominant peak amplifier, but "
            "it is not a byte-by-byte allocator attribution."
        ),
        "next_action": (
            "M2 should first mitigate direct-LU factorization/solve peak memory "
            "without changing physics or acceptance gates; baseline application "
            "memory remains a separate optimization claim."
            if status == "ISSUE220_M1_ATTRIBUTION_READY"
            else "Collect additional phase-resolved evidence before M2."
        ),
    }


def _table_rows(cases: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for level in ("R0", "R1", "R2"):
        case = cases[level]
        problem = case["problem"]
        memory = case["memory"]
        rows.append(
            {
                "level": level,
                "elements": problem.get("elements"),
                "dofs": problem.get("dofs"),
                "jacobian_nnz": None,
                "initial_setup_mb": memory.get("initial_setup_mb"),
                "pre_first_linear_mb": memory.get("pre_first_linear_mb"),
                "first_linear_increment_mb": memory.get("first_linear_increment_mb"),
                "post_first_linear_mb": memory.get("post_first_linear_mb"),
                "peak_resident_mb": memory.get("peak_resident_mb"),
                "peak_mb_per_million_dofs": memory.get("peak_mb_per_million_dofs"),
            }
        )
    return rows


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _write_table(out: Path, rows: list[dict[str, Any]]) -> None:
    csv_path = out / "memory_table.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    md = [
        "| level | elements | DoFs | Jacobian nnz | setup MB | pre-linear MB | first-linear ΔMB | post-linear MB | peak MB | MB/1e6 DoF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        md.append(
            "| {level} | {elements} | {dofs} | {jacobian_nnz} | {initial_setup_mb} | "
            "{pre_first_linear_mb} | {first_linear_increment_mb} | "
            "{post_first_linear_mb} | {peak_resident_mb} | "
            "{peak_mb_per_million_dofs} |".format(
                **{key: _fmt(value) for key, value in row.items()}
            )
        )
    (out / "memory_table.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def analyze(
    artifact_root: Path,
    results_root: Path,
    *,
    source_run_id: int,
    source_head: str,
    artifact_digest: str,
) -> dict[str, Any]:
    logs_root = artifact_root / "logs"
    cases = {
        level: _case_summary(level, logs_root / filename)
        for level, filename in CASE_LOGS.items()
    }
    cross = _cross_level(cases)
    decision = _decision(cases)
    rows = _table_rows(cases)
    results_root.mkdir(parents=True, exist_ok=True)
    _write_table(results_root, rows)
    summary = {
        "schema_version": 1,
        "issue": 220,
        "parent_issue": 219,
        "source_evidence": {
            "workflow_run_id": source_run_id,
            "repository_head": source_head,
            "artifact_digest": artifact_digest,
            "artifact_root": str(artifact_root),
        },
        "cases": cases,
        "cross_level": cross,
        "decision": decision,
        "limitations": [
            "Historical coarse/R0 log did not emit the same detailed setup/Jacobian live-memory sections as R1/R2; unavailable fields remain explicit.",
            "Jacobian nnz is not present in the governed historical artifact and is therefore unavailable rather than inferred.",
            "MOOSE live [MB] values are process-resident memory observations; PerfGraph section Mem(MB) allocation accounting is a distinct metric.",
            "This analysis reuses governed historical production-physics evidence and does not itself execute Physics.",
        ],
    }
    (results_root / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "synthetic.log"
        log.write_text(
            "\n".join(
                [
                    "Mesh:",
                    "  Nodes: 100",
                    "  Elems: 200",
                    "  Num DOFs: 400",
                    "  PETSc Preconditioner:    lu",
                    "\x1b[33mFinished Performing Initial Setup\x1b[0m [ 1.00 s] [ 100 MB]",
                    "Computing Jacobian. [ 2.00 s] [ 150 MB]",
                    "    Linear solve converged due to CONVERGED_RTOL iterations 1",
                    "Computing Residual... [ 1.00 s] [ 500 MB]",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        profile = resident_memory_profile(log)
        transition = profile["first_linear_solve"]
        checks = {
            "sample_count": len(profile["samples"]) == 3,
            "ansi_stripped": profile["initial_setup"]["label"] == "Finished Performing Initial Setup",
            "before": math.isclose(float(transition["before"]["resident_mb"]), 150.0),
            "after": math.isclose(float(transition["after"]["resident_mb"]), 500.0),
            "delta": math.isclose(float(transition["delta_mb"]), 350.0),
            "peak": math.isclose(float(profile["peak"]["resident_mb"]), 500.0),
        }
    failed = sorted(key for key, passed in checks.items() if not passed)
    return {"status": "PASS" if not failed else "FAIL", "checks": checks, "failed": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument(
        "--results-root", type=Path, default=Path("issue220-memory-audit-results")
    )
    parser.add_argument("--source-run-id", type=int, default=EXPECTED_SOURCE_RUN_ID)
    parser.add_argument("--source-head", default=EXPECTED_SOURCE_HEAD)
    parser.add_argument("--artifact-digest", default=EXPECTED_ARTIFACT_DIGEST)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1

    if args.artifact_root is None:
        parser.error("--artifact-root is required unless --self-test")
    summary = analyze(
        args.artifact_root.resolve(),
        args.results_root.resolve(),
        source_run_id=args.source_run_id,
        source_head=args.source_head,
        artifact_digest=args.artifact_digest,
    )
    print((args.results_root.resolve() / "memory_table.md").read_text(encoding="utf-8"))
    print(json.dumps(summary["cross_level"], indent=2, sort_keys=True))
    print(json.dumps(summary["decision"], indent=2, sort_keys=True))
    return 0 if summary["decision"]["status"] == "ISSUE220_M1_ATTRIBUTION_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
