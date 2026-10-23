"""Static semantic role guard: current policy and adversarial examples."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "ci/guards/physics_directory_role_guard.py"
spec = importlib.util.spec_from_file_location("physics_directory_role_guard", GUARD)
assert spec is not None and spec.loader is not None
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def _policy():
    return json.loads((ROOT / "docs/architecture/physics_directory_roles_v1.json").read_text())


def test_all_current_directory_roles_have_a_declared_owner():
    policy = _policy()
    assert len(policy["roles"]) == 15
    found = {p.name for p in (ROOT / "physics_harness").iterdir()
             if p.is_dir() and p.name != "__pycache__"}
    assert found == set(policy["roles"])


def test_current_review_exceptions_are_exact_and_not_blanket_grants():
    files = {p.relative_to(ROOT).as_posix(): p.read_text()
             for p in (ROOT / "physics_harness").rglob("*.py")}
    findings = guard.evaluate(files, _policy())
    violations = [x for x in findings if x["status"] in ("VIOLATION", "NOT_EVALUATED")]
    assert violations == [], violations
    named = {(f["source"], f["code"]) for f in findings}
    assert ("physics_harness/application/gateway.py", "TRANSITIONAL_ROLE_EDGE") not in named
    assert ("physics_harness/application/gateway.py", "OBSOLETE_IMPORT_EXCEPTION") not in named
    assert len(_policy()["import_exceptions"]) == 1
    assert ("physics_harness/application/performance.py", "APPROVED_ROLE_EDGE") in named
    assert ("physics_harness/ontology/sol_runtime_consumer.py", "TRANSITIONAL_PROCESS_CALL") in named


def test_unapproved_moose_reference_fails_even_with_existing_exception():
    policy = _policy()
    files = {f"physics_harness/{role}/__init__.py": "" for role in policy["roles"]}
    files["physics_harness/application/new_gateway.py"] = (
        "from physics_harness.adapters.moose import lower_execution_plan\n"
    )
    findings = guard.evaluate(files, policy)
    assert any(x["code"] == "FORBIDDEN_ROLE_EDGE" and
               x["source"].endswith("/new_gateway.py") for x in findings)


def test_ontology_process_ownership_fails_outside_named_exception():
    policy = _policy()
    files = {f"physics_harness/{role}/__init__.py": "" for role in policy["roles"]}
    files["physics_harness/ontology/new_consumer.py"] = (
        "import subprocess\nsubprocess.run(['echo'])\n"
    )
    findings = guard.evaluate(files, policy)
    assert any(x["code"] == "FORBIDDEN_PROCESS_CALL" for x in findings)


def test_existing_dependency_guard_legacy_target_rules_are_reachable():
    path = ROOT / "ci/guards/physics_dependency_guard.py"
    legacy_spec = importlib.util.spec_from_file_location("physics_dependency_guard", path)
    assert legacy_spec is not None and legacy_spec.loader is not None
    legacy = importlib.util.module_from_spec(legacy_spec)
    legacy_spec.loader.exec_module(legacy)
    assert legacy.violation("physics_harness.evidence.x", "physics_harness.diagnose.y")
    assert legacy.violation("physics_harness.execution.x", "physics_harness.inventory.y")
    assert legacy.violation("physics_harness.execution.x", "physics_harness.dmix.y")
    assert legacy.CANONICAL_PACKAGES.isdisjoint(legacy.LEGACY_TARGET_PACKAGES)
