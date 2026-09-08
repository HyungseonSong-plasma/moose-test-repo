#!/usr/bin/env python3
"""P0 acceptance guard for Issue #79 CLI adapter convergence."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.cli.app import COMMANDS

CENSUS = ROOT / "docs/development/2026-09-02_issue79_cli_wrapper_census.json"
RETIRED = (
    "coupling_evr1_runtime",
    "coupling_evr2_runtime",
    "dmix_equivalence",
)
COMMANDS_UNDER_TEST = ("coupling-evr1", "coupling-evr2", "dmix-equivalence")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _run(*args: str) -> str:
    process = subprocess.run(
        [sys.executable, *args], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if process.returncode != 0:
        raise AssertionError(f"rc={process.returncode}: {' '.join(args)}\n{process.stdout}")
    return process.stdout


def main() -> int:
    census = json.loads(CENSUS.read_text(encoding="utf-8"))
    assert census["issue"] == 79
    assert census["scientific_semantic_impact"] == "NONE"
    assert census["top_level_executable_wrappers_before"] == 3
    assert census["top_level_executable_wrappers_after"] == 0
    assert {row["disposition"] for row in census["candidates"]} == {"RETIRE_AFTER_CLI_MOVE"}

    for leaf in RETIRED:
        assert not (ROOT / "qpx_harness" / f"{leaf}.py").exists(), leaf
    violations = {}
    for path in (ROOT / "qpx_harness").rglob("*.py"):
        found = sorted(module for module in _imports(path) if module.rsplit(".", 1)[-1] in RETIRED)
        if found:
            violations[str(path.relative_to(ROOT))] = found
    assert violations == {}, violations

    for path in (ROOT / "qpx_harness").rglob("*.py"):
        if "cli" in path.parts:
            continue
        assert not any(module == "qpx_harness.cli" or module.startswith("qpx_harness.cli.") for module in _imports(path)), path

    assert set(COMMANDS_UNDER_TEST) <= set(COMMANDS)
    bin_qpx = str(ROOT / "bin/qpx.py")
    for command in COMMANDS_UNDER_TEST:
        assert f"usage: qpx {command}" in _run(bin_qpx, command, "--help")
        assert "PASS" in _run(bin_qpx, command, "--self-test")

    coupling_source = (ROOT / "qpx_harness/cli/commands/coupling.py").read_text()
    dmix_source = (ROOT / "qpx_harness/cli/commands/dmix.py").read_text()
    for marker in ("ISSUE31_EVR1_FATAL", "ISSUE31_EVR2_FATAL"):
        assert marker in coupling_source
    assert "DMIX_EQ_FATAL" in dmix_source
    assert "from qpx_harness.cli import main" in (ROOT / "bin/qpx.py").read_text()

    assert "Issue82 performance ownership guard: PASS" in _run(
        str(ROOT / "tests/Issue82_performance_ownership/final_guard.py")
    )
    assert "ISSUE70_ARCHITECTURE_CENSUS: PASS" in _run(str(ROOT / "tools/qpx_architecture_census.py"))
    assert "ISSUE66_76_FINAL_GUARD: PASS" in _run(
        str(ROOT / "tests/Issue66_76_architecture_convergence/final_guard.py")
    )
    assert "ISSUE48_GENERALITY_SELFTEST: PASS" in _run(
        str(ROOT / "tests/Issue48_qpx_harness_generality/self_test.py")
    )
    assert "QPX_HARNESS_SELFTEST: PASS" in _run(bin_qpx, "self-test")
    print("ISSUE79_CLI_ADAPTER_CONVERGENCE_GUARD: PASS")
    print("Issue79 scientific P3: NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
