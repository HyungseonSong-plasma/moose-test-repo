#!/usr/bin/env python3
"""P0 acceptance guard for Issue #82 performance ownership convergence."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import analysis
from qpx_harness.analysis.performance import cache, investigation, profile
from qpx_harness.cli.app import COMMANDS
from qpx_harness.cli.commands import performance as performance_cli
from qpx_harness.performance import runner, smoke
from qpx_harness.performance.probes import runtime as probe_runtime
from qpx_harness.performance.probes import transport

CENSUS = ROOT / "docs/development/2026-09-02_issue82_performance_ownership_census.json"
RETIRED_PATHS = (
    ROOT / "qpx_harness/performance_core.py",
    ROOT / "qpx_harness/performance_smoke.py",
    ROOT / "qpx_harness/performance_investigation.py",
    ROOT / "qpx_harness/performance_transport_probe_direct.py",
    ROOT / "qpx_harness/performance_cache_audit.py",
    ROOT / "qpx_harness/analysis/performance/legacy.py",
)
RETIRED_LEAVES = {
    "performance_core",
    "performance_smoke",
    "performance_investigation",
    "performance_transport_probe_direct",
    "performance_cache_audit",
    "legacy",
}
CAPABILITY_PATHS = (
    ROOT / "qpx_harness/performance/runner.py",
    ROOT / "qpx_harness/performance/smoke.py",
    ROOT / "qpx_harness/performance/probes/runtime.py",
    ROOT / "qpx_harness/performance/probes/transport.py",
    ROOT / "qpx_harness/analysis/performance/cache.py",
    ROOT / "qpx_harness/analysis/performance/investigation.py",
    ROOT / "qpx_harness/analysis/performance/profile.py",
    ROOT / "qpx_harness/cpp/functor_usage.py",
)
PERFORMANCE_COMMANDS = {
    "measure",
    "measure-smoke",
    "investigate",
    "transport-probe",
    "cache-audit",
    "analyze",
}
SELF_TEST_COMMANDS = PERFORMANCE_COMMANDS - {"analyze"}
EXPECTED_COMMANDS = {
    "test",
    "test-all",
    "coupling-evr1",
    "coupling-evr2",
    "scale-audit",
    "fast-relaxation",
    "fast-coupling-diagnostic",
    "inventory-nullspace",
    "inventory-first-linear",
    "inventory-jacobian-localization",
    "inventory-fd-reference",
    "contract",
    "dmix-equivalence",
    "measure",
    "measure-smoke",
    "investigate",
    "transport-probe",
    "cache-audit",
    "profile",
    "analyze",
    "bundle",
    "inventory",
    "preflight",
    "temporal-csv",
    "self-test",
}


def _import_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _retired_imports(path: Path) -> set[str]:
    return {
        module
        for module in _import_modules(path)
        if module.rsplit(".", 1)[-1] in RETIRED_LEAVES
    }


def _run(*args: str) -> str:
    process = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if process.returncode != 0:
        raise AssertionError(
            f"command failed rc={process.returncode}: {' '.join(args)}\n{process.stdout}"
        )
    return process.stdout


def _check_census() -> dict:
    data = json.loads(CENSUS.read_text(encoding="utf-8"))
    assert data["issue"] == 82
    assert data["baseline_commit"].startswith("e5d8c50")
    assert data["scientific_semantic_impact"] == "NONE"
    assert data["candidate_top_level_owners_before"] == 5
    assert data["candidate_top_level_owners_after"] == 0
    assert len(data["surfaces"]) == 6
    assert all(row["disposition"] for row in data["surfaces"])

    symbols = data["legacy_public_symbol_disposition"]
    assert {row["symbol"] for row in symbols} == {
        "analyze",
        "event_time",
        "load_petsc_events",
        "perfgraph_jacobian_self",
    }
    assert all(row["disposition"] == "PROMOTE_TO_FOCUSED_CAPABILITY" for row in symbols)
    assert data["pf2"]["implemented_slice_in_issue82"] is False
    assert data["pf2"]["issue40_status_claim"] == "UNCHANGED_OPEN_NOT_CLOSED_BY_REFACTOR"
    assert data["validation"]["scientific_p3"] == "NOT_RUN"
    return data


def _check_retirement_and_boundaries() -> None:
    assert not [str(path.relative_to(ROOT)) for path in RETIRED_PATHS if path.exists()]

    production = ROOT / "qpx_harness"
    violations: dict[str, list[str]] = {}
    for path in production.rglob("*.py"):
        retired = sorted(_retired_imports(path))
        if retired:
            violations[str(path.relative_to(ROOT))] = retired
    assert violations == {}, violations

    for path in CAPABILITY_PATHS:
        imports = _import_modules(path)
        assert not any(module == "cli" or ".cli" in module for module in imports), path
        source = path.read_text(encoding="utf-8")
        assert "argparse.ArgumentParser" not in source, path

    cli_source = Path(performance_cli.__file__).read_text(encoding="utf-8")
    for token in (
        'argparse.ArgumentParser(prog="qpx measure")',
        'argparse.ArgumentParser(prog="qpx measure-smoke")',
        'argparse.ArgumentParser(prog="qpx investigate")',
        'argparse.ArgumentParser(prog="qpx transport-probe")',
        'argparse.ArgumentParser(prog="qpx cache-audit")',
        'argparse.ArgumentParser(prog="qpx analyze")',
    ):
        assert token in cli_source, token


def _check_owner_identity_and_cache_split() -> None:
    assert analysis.analyze is profile.analyze
    assert cache.audit_qpx_tree
    assert investigation.build_investigation_summary
    assert runner.run_measurement
    assert smoke.run_smoke_pair
    assert transport.instrument_source
    assert probe_runtime.run_managed_probe

    cpp_source = (ROOT / "qpx_harness/cpp/functor_usage.py").read_text()
    cache_source = Path(cache.__file__).read_text()
    cli_source = Path(performance_cli.__file__).read_text()
    for forbidden in (
        "QPXFVMixtureAveragedDiffusion",
        "NATIVE_FUNCTOR_CACHE_CANDIDATE",
        "MATERIAL_SHARED_RESULT_REQUIRED",
    ):
        assert forbidden not in cpp_source, forbidden
    for forbidden in ("argparse", "write_json_bundle", "utc_timestamp"):
        assert forbidden not in cache_source, forbidden
    for required in (
        "extract_functor_property_declaration",
        "parameter_functor_calls",
    ):
        assert required in cache_source, required
    for required in ("cache.audit_qpx_tree", "write_json_bundle", "_cache_run_root"):
        assert required in cli_source, required

    for symbol in (
        "analyze",
        "event_time",
        "load_petsc_events",
        "perfgraph_jacobian_self",
    ):
        assert callable(getattr(profile, symbol))


def _check_cli_and_validation_surfaces() -> None:
    assert set(COMMANDS) == EXPECTED_COMMANDS
    assert PERFORMANCE_COMMANDS <= set(COMMANDS)

    bin_qpx = str(ROOT / "bin/qpx.py")
    for command in sorted(PERFORMANCE_COMMANDS):
        output = _run(bin_qpx, command, "--help")
        assert f"usage: qpx {command}" in output, (command, output)
    for command in sorted(SELF_TEST_COMMANDS):
        output = _run(bin_qpx, command, "--self-test")
        assert "PASS" in output, (command, output)

    assert "ISSUE70_ARCHITECTURE_CENSUS: PASS" in _run(
        str(ROOT / "tools/qpx_architecture_census.py")
    )
    assert "ISSUE66_76_FINAL_GUARD: PASS" in _run(
        str(ROOT / "tests/Issue66_76_architecture_convergence/final_guard.py")
    )
    assert "ISSUE48_GENERALITY_SELFTEST: PASS" in _run(
        str(ROOT / "tests/Issue48_qpx_harness_generality/self_test.py")
    )
    assert "QPX_HARNESS_SELFTEST: PASS" in _run(bin_qpx, "self-test")


def main() -> int:
    _check_census()
    _check_retirement_and_boundaries()
    _check_owner_identity_and_cache_split()
    _check_cli_and_validation_surfaces()
    print("Issue82 performance ownership guard: PASS")
    print("Issue82 PF2 feature slice: NOT_IMPLEMENTED (#40 remains open)")
    print("Issue82 PF3 feature status: UNCHANGED (#41 remains open)")
    print("Issue82 scientific P3: NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
