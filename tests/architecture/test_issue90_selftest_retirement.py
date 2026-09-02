from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CENSUS = ROOT / "docs/development/2026-09-02_issue90_selftest_census.json"


def test_aggregate_selftest_cli_and_ci_step_are_retired() -> None:
    app = (ROOT / "qpx_harness/cli/app.py").read_text()
    cli_init = (ROOT / "qpx_harness/cli/__init__.py").read_text()
    workflow = (ROOT / ".github/workflows/qpx-cleanup-validation.yml").read_text()
    assert '"self-test"' not in app
    assert "self_test_cli" not in app
    assert "self_test_cli" not in cli_init
    assert "transitional harness self-test" not in workflow.lower()
    assert "python bin/qpx.py self-test" not in workflow


def test_production_runtime_surfaces_do_not_auto_gate_on_selftests() -> None:
    paths = (
        "qpx_harness/issue43_coupling_diagnostic.py",
        "qpx_harness/issue43_fast_relaxation.py",
        "qpx_harness/inventory/cli.py",
        "qpx_harness/cli/commands/coupling.py",
        "qpx_harness/coupling_evr1/orchestration.py",
        "qpx_harness/coupling_evr2/orchestration.py",
    )
    for relative in paths:
        source = (ROOT / relative).read_text()
        assert '"--self-test"' not in source, relative
        assert "if self_test()" not in source, relative
        assert "if inventory_self_test()" not in source, relative
        assert "if first_linear_self_test()" not in source, relative
    evr2 = (ROOT / "qpx_harness/coupling_evr2/orchestration.py").read_text()
    assert "_canonical_checker_self_test" not in evr2
    assert "kg_e_checker_selftest" not in evr2


def test_issue43_45_guard_is_static_not_selftest_runner() -> None:
    source = (ROOT / "experiments/Issue43_45_science_refactor/final_guard.py").read_text()
    assert ".self_test()" not in source


def test_accepted_electron_checker_characterization_runs_in_pytest() -> None:
    checker = ROOT / "experiments/Issue2_electron_bulk_drift/check_case.py"
    proc = subprocess.run(
        [sys.executable, str(checker), "--self-test"],
        cwd=checker.parent,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "R2_CASE_CHECKER_SELFTEST: PASS" in proc.stdout


def test_machine_readable_census_matches_pytest_authority() -> None:
    data = json.loads(CENSUS.read_text())
    assert data["schema_version"] == 1
    assert data["direct_qpx_selftest_entrypoint_count"] == 21
    assert data["aggregate_cli_retired"] is True
    assert data["ci_transitional_step_retired"] is True
    assert data["pytest_authority"] == "tests/characterization/test_qpx_legacy_selftests.py"
    assert all(row["qpx_required"] is False for row in data["entrypoints"])
    assert all(row["ci_eligible"] is True for row in data["entrypoints"])
    assert all(row["runtime_gate"] is False for row in data["entrypoints"])
    assert data["remaining_runtime_gate_blockers"] == []
    assert data["scientific_p3_run_by_migration"] is False
    assert data["scientific_evr_consumed_by_migration"] == 0
