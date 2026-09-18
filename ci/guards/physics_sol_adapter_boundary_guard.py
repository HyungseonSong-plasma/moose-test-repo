#!/usr/bin/env python3
"""Guard the long-range Physics -> SOL adapter boundary migration.

This guard freezes current semantic-control-plane debt without pretending the
cross-repository cutover is already complete. It intentionally does not scan
explicit MOOSE-specific operational utilities such as CLI preflight or
performance decoding; those are separate MOOSE_GENERIC migration surfaces.
"""
from __future__ import annotations

import argparse
import ast
import re
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

# These categories are owned by simulation-ontology/sol-adapter-runtime. Match
# path components by normalized tokens so spelling variants cannot create a
# second Physics-local owner under a slightly different filename.
FORBIDDEN_LOCAL_OWNER_TOKEN_GROUPS = (
    frozenset({"adapter", "runtime"}),
    frozenset({"adapter", "transport"}),
    frozenset({"adapter", "registry"}),
    frozenset({"adapter", "session"}),
    frozenset({"json", "rpc", "transport"}),
    frozenset({"process", "lifecycle"}),
    frozenset({"session", "lifecycle"}),
    frozenset({"adapter", "compatibility"}),
    frozenset({"adapter", "selector"}),
    frozenset({"response", "loss"}),
)
FORBIDDEN_EXECUTION_PLAN_IDENTITIES = (
    "MooseTargetIR",
    "MooseCaseIR",
    "MappingPlan",
    "RealizationSpec",
    "adapter_protocol_version",
    "public_contract_version",
)
FORBIDDEN_EXECUTION_PLAN_IDENTITY_KEYS = {
    re.sub(r"[^a-z0-9]", "", value.lower())
    for value in FORBIDDEN_EXECUTION_PLAN_IDENTITIES
}


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _module_package(path: Path) -> tuple[str, ...]:
    relative = path.relative_to(ROOT).with_suffix("")
    return relative.parts[:-1]


def _import_modules_from_tree(tree: ast.AST, package: tuple[str, ...]) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue

        if node.level:
            if node.level > len(package):
                continue
            keep = len(package) - node.level + 1
            base_parts = package[:keep]
        else:
            base_parts = ()
        if node.module:
            base_parts += tuple(node.module.split("."))
        base = ".".join(base_parts)
        if base:
            modules.add(base)
        for alias in node.names:
            if alias.name == "*":
                continue
            imported = ".".join(part for part in (base, alias.name) if part)
            if imported:
                modules.add(imported)
    return modules


def _import_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return _import_modules_from_tree(tree, _module_package(path))


def _semantic_paths() -> list[Path]:
    paths = [GATEWAY]
    for directory in SEMANTIC_DIRS:
        paths.extend(sorted(directory.rglob("*.py")))
    return sorted({path for path in paths if path.is_file()})


def _is_moose_import(module: str) -> bool:
    return module == MOOSE_PREFIX or module.startswith(MOOSE_PREFIX + ".")


def _path_tokens(path: Path) -> set[str]:
    tokens: set[str] = set()
    for part in path.parts:
        tokens.update(token for token in re.split(r"[^a-z0-9]+", part.lower()) if token)
    return tokens


def _is_forbidden_local_owner(path: Path) -> bool:
    tokens = _path_tokens(path)
    return any(group <= tokens for group in FORBIDDEN_LOCAL_OWNER_TOKEN_GROUPS)


def _runtime_owner_paths() -> list[str]:
    violations: list[str] = []
    for path in HARNESS.rglob("*"):
        if "__pycache__" in path.parts or not _is_forbidden_local_owner(path):
            continue
        if path.is_file():
            violations.append(_rel(path))
        elif path.is_dir():
            violations.append(_rel(path) + "/")
    return sorted(set(violations))


def _semantic_moose_edges() -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for path in _semantic_paths():
        for module in _import_modules(path):
            if _is_moose_import(module):
                # Normalize submodule/alias imports to the architectural owner.
                edges.add((_rel(path), MOOSE_PREFIX))
    return edges


def _identity_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _annotation_identifiers(node: ast.AST | None) -> set[str]:
    if node is None:
        return set()
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def _state_target_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name) and child.value.id == "self":
            names.add(child.attr)
    return names


def _execution_plan_conflations_from_tree(tree: ast.Module) -> list[str]:
    found: set[str] = set()
    plan = next(
        (node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ExecutionPlan"),
        None,
    )
    if plan is None:
        return ["ExecutionPlan<missing>"]

    def inspect(name: str) -> None:
        if _identity_key(name) in FORBIDDEN_EXECUTION_PLAN_IDENTITY_KEYS:
            found.add(name)

    for statement in plan.body:
        if isinstance(statement, ast.AnnAssign):
            for name in _state_target_names(statement.target):
                inspect(name)
            for name in _annotation_identifiers(statement.annotation):
                inspect(name)
        elif isinstance(statement, (ast.Assign, ast.AugAssign)):
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            for target in targets:
                for name in _state_target_names(target):
                    inspect(name)
        elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in (*statement.args.posonlyargs, *statement.args.args, *statement.args.kwonlyargs):
                for name in _annotation_identifiers(arg.annotation):
                    inspect(name)
            for name in _annotation_identifiers(statement.returns):
                inspect(name)
            if statement.name == "__init__":
                for child in ast.walk(statement):
                    if isinstance(child, ast.AnnAssign):
                        for name in _state_target_names(child.target):
                            inspect(name)
                        for name in _annotation_identifiers(child.annotation):
                            inspect(name)
                    elif isinstance(child, (ast.Assign, ast.AugAssign)):
                        targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                        for target in targets:
                            for name in _state_target_names(target):
                                inspect(name)
    return sorted(found)


def _execution_plan_conflations() -> list[str]:
    path = HARNESS / "execution" / "plan.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return _execution_plan_conflations_from_tree(tree)


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

    import_cases = (
        ("from physics_harness.adapters import moose", ("physics_harness", "planning")),
        ("from physics_harness.adapters.moose import target", ("physics_harness", "planning")),
        ("from ..adapters import moose", ("physics_harness", "planning")),
        ("from ..adapters.moose import target", ("physics_harness", "planning")),
    )
    for source, package in import_cases:
        modules = _import_modules_from_tree(ast.parse(source), package)
        if not any(_is_moose_import(module) for module in modules):
            errors.append(f"self-test failed to resolve MOOSE ImportFrom: {source}")

    owner_cases = (
        "adapter_runtime.py",
        "adapter_transport.py",
        "adapter_registry.py",
        "adapter_session.py",
        "json_rpc_transport.py",
        "process_lifecycle.py",
        "session_lifecycle.py",
        "adapter_compatibility.py",
        "adapter_selector.py",
        "response_loss.py",
    )
    for name in owner_cases:
        if not _is_forbidden_local_owner(Path(name)):
            errors.append(f"self-test failed local-owner category: {name}")
    if _is_forbidden_local_owner(Path("moose_performance_decoder.py")):
        errors.append("self-test falsely classified MOOSE-specific operational utility")

    if ("physics_harness/application/gateway.py", MOOSE_PREFIX) not in EXPECTED_TRANSITIONAL_MOOSE_EDGES:
        errors.append("self-test lost the declared transitional gateway edge")
    if len(EXPECTED_TRANSITIONAL_MOOSE_EDGES) != 1:
        errors.append("self-test expects exactly one transitional semantic MOOSE edge")

    synthetic_plan = ast.parse(
        "class ExecutionPlan:\n"
        "    mapping_plan: int\n"
        "    realization_spec: str\n"
        "    def __init__(self):\n"
        "        self.moose_target_ir = None\n"
    )
    conflations = _execution_plan_conflations_from_tree(synthetic_plan)
    for expected in ("mapping_plan", "realization_spec", "moose_target_ir"):
        if expected not in conflations:
            errors.append(f"self-test missed normalized ExecutionPlan identity: {expected}")

    harmless_doc = ast.parse(
        "class ExecutionPlan:\n"
        "    \"\"\"ExecutionPlan is not a MappingPlan or RealizationSpec.\"\"\"\n"
        "    plan_id: str\n"
    )
    if _execution_plan_conflations_from_tree(harmless_doc):
        errors.append("self-test treated ExecutionPlan documentation as identity state")

    return errors


def _check() -> list[str]:
    errors: list[str] = []

    runtime_owners = _runtime_owner_paths()
    if runtime_owners:
        errors.append(
            "Physics-local adapter runtime/transport/registry/lifecycle/compatibility/selector/response-loss "
            "ownership is forbidden; reuse simulation-ontology sol-adapter-runtime: "
            f"{runtime_owners}"
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
        errors.append(f"semantic control plane acquired new direct MOOSE dependencies: {extra}")

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
