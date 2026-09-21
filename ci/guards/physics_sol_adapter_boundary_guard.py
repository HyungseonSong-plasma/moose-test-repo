#!/usr/bin/env python3
"""Guard the Physics semantic control plane after the #280 SOL cutover."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "physics_harness"
GATEWAY = HARNESS / "application" / "gateway.py"
SEMANTIC_DIRS = (HARNESS / "specification", HARNESS / "planning", HARNESS / "execution", HARNESS / "ontology")
MOOSE_PREFIX = "physics_harness.adapters.moose"
FORBIDDEN_EXECUTION_PLAN_IDENTITIES = {"MooseTargetIR", "MooseCaseIR", "MappingPlan", "RealizationSpec", "adapter_protocol_version", "public_contract_version"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = path.relative_to(ROOT).with_suffix("").parts[:-1]
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base_parts = package[:max(len(package) - node.level + 1, 0)] if node.level else ()
            if node.module:
                base_parts += tuple(node.module.split("."))
            base = ".".join(base_parts)
            if base:
                modules.add(base)
            for alias in node.names:
                if alias.name != "*":
                    modules.add(".".join(part for part in (base, alias.name) if part))
    return modules


def _semantic_paths() -> list[Path]:
    paths = [GATEWAY]
    for directory in SEMANTIC_DIRS:
        paths.extend(directory.rglob("*.py"))
    return sorted({path for path in paths if path.is_file()})


def _semantic_moose_edges() -> list[str]:
    violations: list[str] = []
    for path in _semantic_paths():
        for module in _imports(path):
            if module == MOOSE_PREFIX or module.startswith(MOOSE_PREFIX + "."):
                violations.append(f"{path.relative_to(ROOT).as_posix()} -> {module}")
    return sorted(set(violations))


def _execution_plan_conflations() -> list[str]:
    path = HARNESS / "execution" / "plan.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    plan = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ExecutionPlan"), None)
    if plan is None:
        return ["ExecutionPlan<missing>"]
    found: set[str] = set()
    for node in ast.walk(plan):
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_EXECUTION_PLAN_IDENTITIES:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_EXECUTION_PLAN_IDENTITIES:
            found.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in FORBIDDEN_EXECUTION_PLAN_IDENTITIES:
            found.add(node.value)
    return sorted(found)


def main() -> int:
    errors: list[str] = []
    edges = _semantic_moose_edges()
    if edges:
        errors.append("semantic control-plane direct MOOSE edges must be zero: " + ", ".join(edges))
    conflations = _execution_plan_conflations()
    if conflations:
        errors.append("ExecutionPlan must not absorb SOL/MOOSE contract identities: " + ", ".join(conflations))
    if errors:
        for error in errors:
            print(f"PHYSICS_SOL_ADAPTER_BOUNDARY_GUARD: FAIL: {error}")
        return 1
    print("PHYSICS_SOL_ADAPTER_BOUNDARY_GUARD: PASS")
    print("DIRECT_APPLICATION_TO_LOCAL_MOOSE_IMPLEMENTATION=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
