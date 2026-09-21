#!/usr/bin/env python3
"""P0 guard for Issue #84 live noncanonical-owner migration."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CENSUS = ROOT / "docs/development/2026-09-02_issue84_live_owner_migration_census.json"
OLD = (
    "moose_input", "output_observation_contract", "preflight", "perfgraph",
    "temporal", "status", "reporting", "regression", "profiling",
)
NEW = (
    "qpx_harness/moose/input.py", "qpx_harness/moose/output_observation.py",
    "qpx_harness/moose/preflight.py", "qpx_harness/analysis/performance/perfgraph.py",
    "qpx_harness/analysis/temporal.py", "qpx_harness/execution/status.py",
    "qpx_harness/execution/reporting.py", "qpx_harness/execution/regression.py",
    "qpx_harness/performance/profiling.py",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _run(*args: str) -> str:
    proc = subprocess.run([sys.executable, *args], cwd=ROOT, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if proc.returncode:
        raise AssertionError(f"rc={proc.returncode}: {' '.join(args)}\n{proc.stdout}")
    return proc.stdout


def main() -> int:
    data = json.loads(CENSUS.read_text())
    assert data["issue"] == 84
    assert data["scientific_semantic_impact"] == "NONE"
    assert data["owners_migrated"] == len(OLD) == len(NEW)
    assert data["unresolved_ownership_blockers"] == 0
    for old in OLD:
        assert not (ROOT / "qpx_harness" / f"{old}.py").exists(), old
    for new in NEW:
        assert (ROOT / new).is_file(), new
    stale = {}
    for base in (ROOT / "qpx_harness", ROOT / "recipes"):
        for path in base.rglob("*.py"):
            hits = sorted(m for m in _imports(path) if m.startswith("qpx_harness.") and m.split(".")[1] in OLD)
            if hits:
                stale[str(path.relative_to(ROOT))] = hits
    assert stale == {}, stale
    assert "ISSUE70_ARCHITECTURE_CENSUS: PASS" in _run(str(ROOT / "tools/qpx_architecture_census.py"))
    assert "ISSUE66_76_FINAL_GUARD: PASS" in _run(str(ROOT / "tests/Issue66_76_architecture_convergence/final_guard.py"))
    assert "ISSUE48_GENERALITY_SELFTEST: PASS" in _run(str(ROOT / "tests/Issue48_qpx_harness_generality/self_test.py"))
    assert "QPX_HARNESS_SELFTEST: PASS" in _run(str(ROOT / "bin/qpx.py"), "self-test")
    print("ISSUE84_LIVE_OWNER_MIGRATION_GUARD: PASS")
    print("Issue84 scientific P3: NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
