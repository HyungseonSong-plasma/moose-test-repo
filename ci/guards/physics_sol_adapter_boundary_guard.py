#!/usr/bin/env python3
"""Guard the long-range Physics -> SOL adapter boundary migration.

This guard freezes current semantic-control-plane debt without pretending the
cross-repository cutover is already complete.  It intentionally does not scan
explicit MOOSE-specific operational utilities such as CLI preflight or
performance decoding; those are separate MOOSE_GENERIC migration surfaces.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "physics_harness"

GATEWAY = HARNESS / "application" / "gateway.py"
SEMANTIC_DIRS = (
    HARNESS / "specification",
    HARNESS / "planning",
    HARNESS / "execution",
    HARNESS / "ontology",
)

MOOSE_PREFIX = "physics_harness.adapters.moose"
EXPECTED_TRANSITIONAL_MOOSE_EDGES = {
    ("physics_harness/application/gateway.py", MOOSE_PREFIX),
}

FORBIDDEN_LOCAL_RUNTIME_FILES = {
    "adapter_runtime.py",
    "adapter_transport.py",
    "adapter_registry.py",
    "adapter_session.py",
}
FORBIDDEN_LOCAL_RUNTIME_DIRS = {
    "adapter_runtime",
    "adapter_transport",
    "adapter_registry",
    "adapter_session",
}
FORBIDDEN_EXECUTION_PLAN_CONFLATION_TOKENS = (
    "MooseTargetIR",
    "MooseCaseIR",
    "MappingPlan",
    "RealizationSpec",
    "adapter_protocol_version",
    "public_contract_version",
)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _import_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module)
    return modules


def _semantic_paths() -> list[Path]:
    paths = [GATEWAY]
    for directory in SEMANTIC_DIRS:
        paths.extend(sorted(directory.rglob("*.py")))
    return sorted({path for path in paths if path.is_file()})


def _is_moose_import(module: str) -> bool:
    return module == MOOSE_PREFIX or module.startswith(MOOSE_PREFIX + ".")


def _runtime_owner_paths() -> list[str]:
    violations: list[str] = []
    for path in HARNESS.rglob("*"):
        if "__pycache__" in path.parts:
            continue
        if path.is_file() and path.name in FORBIDDEN_LOCAL_RUNTIME_FILES:
            violations.append(_rel(path))
        elif path.is_dir() and path.name in FORBIDDEN_LOCAL_RUNTIME_DIRS:
            violations.append(_rel(path) + "/")
    return sorted(set(violations))


def _semantic_moose_edges() -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for path in _semantic_paths():
        for module in _import_modules(path):
            if _is_moose_import(module):
                edges.add((_rel(path), module))
    return edges


def _execution_plan_conflations() -> list[str]:
    path = HARNESS / "execution" / "plan.py"
    text = path.read_text(encoding="utf-8")
    return [token for token in FORBIDDEN_EXECUTION_PLAN_CONFLATION_TOKENS if token in text]


def _self_test() -> list[str]:
    errors: list[str] = []

    positive = (
        MOOSE_PREFIX,
        "physics_harness.adapters.moose.target",
        "physics_harness.adapters.moose.performance.profile",
    )
    negative = (
        "physics_harness.execution",
        "physics_harness.adapters.petsc",
        "simulation_ontology.adapter_runtime",
    )
    for module in positive:
        if not _is_moose_import(module):
            errors.append(f"self-test failed to classify MOOSE import: {module}")
    for module in negative:
        if _is_moose_import(module):
            errors.append(f"self-test falsely classified non-MOOSE import: {module}")

    synthetic_bad_files = {
        "adapter_runtime.py",
        "adapter_transport.py",
        "adapter_registry.py",
        "adapter_session.py",
    }
    if synthetic_bad_files != FORBIDDEN_LOCAL_RUNTIME_FILES:
        errors.append("self-test runtime-owner file set changed unexpectedly")

    if ("physics_harness/application/gateway.py", MOOSE_PREFIX) not in EXPECTED_TRANSITIONAL_MOOSE_EDGES:
        errors.append("self-test lost the declared transitional gateway edge")
    if len(EXPECTED_TRANSITIONAL_MOOSE_EDGES) != 1:
        errors.append("self-test expects exactly one transitional semantic MOOSE edge")

    if "MappingPlan" not in FORBIDDEN_EXECUTION_PLAN_CONFLATION_TOKENS:
        errors.append("self-test no longer protects ExecutionPlan/MappingPlan distinction")
    if "RealizationSpec" not in FORBIDDEN_EXECUTION_PLAN_CONFLATION_TOKENS:
        errors.append("self-test no longer protects ExecutionPlan/RealizationSpec distinction")

    return errors


def _check() -> list[str]:
    errors: list[str] = []

    runtime_owners = _runtime_owner_paths()
    if runtime_owners:
        errors.append(
            "Physics-local adapter runtime/transport/registry ownership is forbidden; "
            f"reuse simulation-ontology sol-adapter-runtime: {runtime_owners}"
        )

    actual_edges = _semantic_moose_edges()
    missing = sorted(EXPECTED_TRANSITIONAL_MOOSE_EDGES - actual_edges)
    extra = sorted(actual_edges - EXPECTED_TRANSITIONAL_MOOSE_EDGES)
    if missing:
        errors.append(
            "declared transitional semantic MOOSE edge disappeared; tighten the guard to zero "
            f"instead of silently changing the baseline: {missing}"
        )
    if extra:
        errors.append(
            "semantic control plane acquired new direct MOOSE dependencies: "
            f"{extra}"
        )

    conflations = _execution_plan_conflations()
    if conflations:
        errors.append(
            "solver-independent ExecutionPlan absorbed target/public-contract identity "
            f"instead of using an explicit interop boundary: {conflations}"
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if not args.self_test and not args.check:
        args.check = True

    errors: list[str] = []
    if args.self_test:
        errors.extend(_self_test())
    if args.check:
        errors.extend(_check())

    if errors:
        print("PHYSICS_SOL_ADAPTER_BOUNDARY_GUARD: FAIL")
        for error in errors:
            print(error)
        return 1

    if args.self_test:
        print("PHYSICS_SOL_ADAPTER_BOUNDARY_GUARD_SELF_TEST: PASS")
    if args.check:
        edges = sorted(_semantic_moose_edges())
        print("PHYSICS_SOL_ADAPTER_BOUNDARY_GUARD: PASS")
        print(f"SEMANTIC_CONTROL_PLANE_DIRECT_MOOSE_EDGE_COUNT={len(edges)}")
        print(f"SEMANTIC_CONTROL_PLANE_DIRECT_MOOSE_EDGES={edges!r}")
        print("PHYSICS_LOCAL_ADAPTER_RUNTIME_OWNER_COUNT=0")
        print("PHYSICS_LOCAL_ADAPTER_TRANSPORT_OWNER_COUNT=0")
        print("PHYSICS_LOCAL_ADAPTER_REGISTRY_OWNER_COUNT=0")
        print("EXECUTION_PLAN_EQ_MAPPING_PLAN=false")
        print("EXECUTION_PLAN_EQ_REALIZATION_SPEC=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
