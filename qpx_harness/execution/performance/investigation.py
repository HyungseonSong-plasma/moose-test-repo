"""Execution orchestration for PF-3 performance investigation."""
from __future__ import annotations

import json
from pathlib import Path

from qpx_harness.analysis.performance.investigation import (
    PerformanceInvestigationError, _load_json, build_investigation_summary, discover_latest_smoke,
)
from qpx_harness.execution.runtime import resolve_executable, validate_executable
from qpx_harness.execution.performance.smoke import default_results_root


def run_investigation(*, run_root: Path | None = None, executable: str | Path | None = None, results_root: Path | None = None) -> int:
    if run_root is None:
        exe = resolve_executable(executable)
        validate_executable(exe)
        root = discover_latest_smoke(results_root if results_root is not None else default_results_root(exe))
    else:
        root = Path(run_root).expanduser().resolve()
        if not root.is_dir():
            raise PerformanceInvestigationError(f"run root does not exist: {root}")

    smoke = _load_json(root / "smoke_summary.json", "smoke summary")
    if smoke.get("pass") is not True:
        raise PerformanceInvestigationError("PF-1 smoke summary is not PASS")
    benchmark = _load_json(root / "benchmark" / "result.json", "benchmark result")
    profile = _load_json(root / "profile" / "result.json", "profile result")
    summary = build_investigation_summary(benchmark, profile, smoke)
    summary["run_root"] = str(root)
    output = root / "investigation_summary.json"
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    classification = summary["classification"]
    print(f"PF3_INVESTIGATION_ROOT: {root}")
    print(f"PF3_ANALYSIS_STATUS: {summary['analysis_status']}")
    print(f"PF3_OUTCOME: {classification['outcome']}")
    print(f"PF3_BOTTLENECK: {classification.get('bottleneck_class') or 'UNRESOLVED'}")
    print(f"PF3_CONFIDENCE: {classification['confidence']}")
    print(f"PF3_REASON: {classification['reason']}")
    if summary.get("profile_to_benchmark_ratio") is not None:
        print(f"PF3_PROFILE_OVERHEAD_RATIO: {summary['profile_to_benchmark_ratio']:.4f}")
    print("PF3_TOP_SECTIONS:")
    for node in summary["top_perfgraph_sections"][:8]:
        print(f"  {node['self_seconds']:.6g}s  calls={node.get('num_calls')}  {node['name']}")
    print(f"PF3_INVESTIGATION_SUMMARY: {output}")
    return 0 if summary["analysis_status"] == "PASS" else 2
