#!/usr/bin/env python3
"""Minimal post-cleanup code-surface acceptance guard for Issue #81."""
from __future__ import annotations
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REGISTER = ROOT / "docs/development/2026-09-02_issue81_minimal_surface_retention_register.json"
CENSUS83 = ROOT / "docs/development/2026-09-02_issue83_dependency_released_retirement_census.json"
CENSUS84 = ROOT / "docs/development/2026-09-02_issue84_live_owner_migration_census.json"

PRODUCTION_CLASSES = {
    "CANONICAL_CAPABILITY",
    "SCIENTIFIC_POLICY",
    "CLI_PRESENTATION",
    "ACTIVE_FEATURE_OWNER",
    "REQUIRED_COMPATIBILITY",
    "DEFERRED_WITH_LIVE_BLOCKER",
    "RETIREMENT_DEFECT",
}
TEST_CLASSES = {
    "CURRENT_REGRESSION",
    "SCIENTIFIC_CHARACTERIZATION",
    "ARCHITECTURE_INVARIANT_GUARD",
    "ACTIVE_FEATURE_VALIDATION",
    "HISTORICAL_REPRODUCTION_JUSTIFIED",
    "RETIREMENT_DEFECT",
}


def _load() -> dict:
    data = json.loads(REGISTER.read_text(encoding="utf-8"))
    assert data["issue"] == 81
    assert data["dependency_chain"] == [77, 78, 82, 79, 84, 80, 83]
    assert data["scientific_semantic_impact"] == "NONE"
    assert data["scientific_p3"] == "NOT_RUN"
    return data


def _classify_production(rel: str, data: dict) -> str:
    if rel in data["canonical_package_surface"]:
        return "CANONICAL_CAPABILITY"
    if any(rel.startswith(prefix) for prefix in data["canonical_capability_prefixes"]):
        return "CANONICAL_CAPABILITY"
    if any(rel.startswith(prefix) for prefix in data["cli_presentation_prefixes"]):
        return "CLI_PRESENTATION"
    if any(rel.startswith(prefix) for prefix in data["scientific_recipe_prefixes"]):
        return "SCIENTIFIC_POLICY"
    exact = {row["path"]: row["owner_class"] for row in data["retention_register"]}
    if rel in exact:
        return exact[rel]
    for row in data["retention_prefix_register"]:
        if rel.startswith(row["path_prefix"]):
            return row["owner_class"]
    return "RETIREMENT_DEFECT"


def _issue_number(rel: str) -> int | None:
    parts = Path(rel).parts
    top = parts[1] if len(parts) > 1 else ""
    match = re.match(r"Issue(\d+)", top)
    return int(match.group(1)) if match else None


def _classify_test(rel: str) -> str:
    number = _issue_number(rel)
    if number is None:
        return "CURRENT_REGRESSION"
    name = Path(rel).name.lower()
    if number <= 46:
        return "SCIENTIFIC_CHARACTERIZATION"
    if number == 48:
        if any(token in name for token in ("issue31", "issue43", "issue45", "issue46")):
            return "SCIENTIFIC_CHARACTERIZATION"
        return "CURRENT_REGRESSION"
    if 47 <= number <= 84:
        return "ARCHITECTURE_INVARIANT_GUARD"
    return "CURRENT_REGRESSION"


def _production_census(data: dict) -> Counter:
    counts: Counter = Counter()
    defects: list[str] = []
    for root_name in ("qpx_harness", "recipes", "bin"):
        root = ROOT / root_name
        for path in root.rglob("*.py"):
            rel = str(path.relative_to(ROOT))
            owner_class = _classify_production(rel, data)
            assert owner_class in PRODUCTION_CLASSES
            counts[owner_class] += 1
            if owner_class == "RETIREMENT_DEFECT":
                defects.append(rel)
    assert defects == [], defects
    return counts


def _test_census() -> Counter:
    counts: Counter = Counter()
    defects: list[str] = []
    for path in (ROOT / "tests").rglob("*.py"):
        rel = str(path.relative_to(ROOT))
        owner_class = _classify_test(rel)
        assert owner_class in TEST_CLASSES
        counts[owner_class] += 1
        if owner_class == "RETIREMENT_DEFECT":
            defects.append(rel)
    assert defects == [], defects
    return counts


def _check_register_contracts(data: dict) -> None:
    for row in data["retention_register"]:
        assert (ROOT / row["path"]).is_file(), row["path"]
        assert row["owner_class"] in PRODUCTION_CLASSES - {"RETIREMENT_DEFECT"}
        assert row["current_consumer_or_invariant"]
        assert row["why_retained"]
        assert "future_retirement_trigger" in row
    for row in data["retention_prefix_register"]:
        assert (ROOT / row["path_prefix"].rstrip("/")).is_dir(), row["path_prefix"]
        assert row["owner_class"] in PRODUCTION_CLASSES - {"RETIREMENT_DEFECT"}
        assert row["current_consumer_or_invariant"]
        assert row["why_retained"]


def _check_dependency_acceptance() -> None:
    census84 = json.loads(CENSUS84.read_text(encoding="utf-8"))
    assert census84["unresolved_ownership_blockers"] == 0
    census83 = json.loads(CENSUS83.read_text(encoding="utf-8"))
    assert census83["acceptance"]["eligible_retirement_residual_count"] == 0
    assert census83["summary"]["retirement_blocker_defects"] == 0
    assert all(
        row["terminal_class"] not in {"RETIRE_NOW", "RETIREMENT_BLOCKER_DEFECT"}
        for row in census83["candidates"]
    )
    assert not (ROOT / "qpx_harness/performance_transport_probe_runtime.py").exists()
    assert not (ROOT / "scripts/qpx.py").exists()


def _check_namespace_collisions() -> None:
    collisions: list[str] = []
    for py_path in (ROOT / "qpx_harness").rglob("*.py"):
        if py_path.name == "__init__.py":
            continue
        package = py_path.with_suffix("")
        if package.is_dir():
            collisions.append(str(py_path.relative_to(ROOT)))
    assert collisions == [], collisions


def _check_issue80_retirements() -> None:
    census80 = json.loads(
        (ROOT / "docs/development/2026-09-02_issue80_migration_test_retirement_census.json").read_text(
            encoding="utf-8"
        )
    )
    deleted = {
        path
        for path, disposition in census80["dispositions"].items()
        if disposition in {"PROMOTE_INVARIANT_THEN_RETIRE", "RETIRE_SUPERSEDED_MIGRATION_ONLY"}
    }
    assert len(deleted) == 19
    assert all(not (ROOT / path).exists() for path in deleted)


def _run(*args: str) -> str:
    process = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if process.returncode:
        raise AssertionError(
            f"rc={process.returncode}: {' '.join(args)}\n{process.stdout}"
        )
    return process.stdout


def _safety_net() -> None:
    assert "ISSUE83_DEPENDENCY_RELEASED_RETIREMENT_GUARD: PASS" in _run(
        str(ROOT / "tests/Issue83_dependency_released_retirement/final_guard.py")
    )
    assert "ISSUE79_CLI_ADAPTER_CONVERGENCE_GUARD: PASS" in _run(
        str(ROOT / "tests/Issue79_cli_adapter_convergence/final_guard.py")
    )
    assert "Issue82 performance ownership guard: PASS" in _run(
        str(ROOT / "tests/Issue82_performance_ownership/final_guard.py")
    )
    assert "ISSUE84_LIVE_OWNER_MIGRATION_GUARD: PASS" in _run(
        str(ROOT / "tests/Issue84_live_owner_migration/final_guard.py")
    )
    architecture = _run(str(ROOT / "tools/qpx_architecture_census.py"))
    assert "ISSUE70_ARCHITECTURE_CENSUS: PASS" in architecture
    assert "QPX_HARNESS_SELFTEST: PASS" in _run(
        str(ROOT / "bin/qpx.py"), "self-test"
    )


def main() -> int:
    data = _load()
    _check_register_contracts(data)
    _check_dependency_acceptance()
    _check_namespace_collisions()
    _check_issue80_retirements()
    production = _production_census(data)
    tests = _test_census()
    _safety_net()
    print("ISSUE81_PRODUCTION_OWNER_COUNTS:", dict(sorted(production.items())))
    print("ISSUE81_TEST_OWNER_COUNTS:", dict(sorted(tests.items())))
    print("ISSUE81_MINIMAL_SURFACE_ACCEPTANCE_GUARD: PASS")
    print("Issue81 retirement defects: 0")
    print("Issue81 scientific P3: NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
