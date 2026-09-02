#!/usr/bin/env python3
"""P0 acceptance guard for Issue #78 mixed-owner decomposition."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CENSUS = ROOT / "docs/development/2026-09-02_issue78_evr2_symbol_census.json"
ADAPTER = ROOT / "qpx_harness/cli/commands/coupling.py"
POLICY = ROOT / "qpx_harness/coupling_evr2/orchestration.py"
GENERIC = (
    ROOT / "qpx_harness/evidence/artifacts.py",
    ROOT / "qpx_harness/diagnostics/nonlinear_solver.py",
    ROOT / "qpx_harness/performance/runner.py",
    ROOT / "qpx_harness/performance/smoke.py",
)


def _defined(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }


def main() -> int:
    data = json.loads(CENSUS.read_text(encoding="utf-8"))
    assert data["issue"] == 78
    assert data["scientific_semantic_impact"] == "NONE"
    assert len(data["symbols"]) == 20
    assert all(row["disposition"] for row in data["symbols"])

    adapter_symbols = _defined(ADAPTER)
    assert {"coupling_evr1_main", "coupling_evr2_main"} <= adapter_symbols

    removed = {
        "_load_json",
        "_create_root",
        "_stage_transport_case",
        "_failure_signature",
        "_result_status",
    }
    policy_symbols = _defined(POLICY)
    assert not (removed & policy_symbols), removed & policy_symbols
    assert {"run", "self_test", "_stage_kg_e", "_manifest"} <= policy_symbols

    policy_source = POLICY.read_text(encoding="utf-8")
    for required in (
        "create_collision_safe_directory",
        "measurement_failure_signature",
        "run_managed_measurement",
        "result_status",
        "run_command",
        "recipe.configured_transport_input",
        "recipe.classify_evr2",
    ):
        assert required in policy_source, required
    for forbidden in (
        "subprocess.run",
        "run_measurement(",
        "def _load_json",
        "def _create_root",
        "def _stage_transport_case",
        "def _failure_signature",
        "def _result_status",
    ):
        assert forbidden not in policy_source, forbidden

    for path in GENERIC:
        source = path.read_text(encoding="utf-8")
        for leaked in ("Issue31", "issue31", "DT_1E6", "DT_1E8", "KG_E"):
            assert leaked not in source, f"{path}: {leaked}"

    proc = subprocess.run(
        [sys.executable, str(ROOT / "bin/qpx.py"), "coupling-evr2", "--self-test"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout
    assert "ISSUE31_EVR2_RUNTIME_SELFTEST: PASS" in proc.stdout
    print("Issue78 EVR2 decomposition guard: PASS")
    print("Issue78 scientific P3: NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
