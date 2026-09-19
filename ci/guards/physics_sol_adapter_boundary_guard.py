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
    """Return a repository-relative POSIX path."""
    return path.relative_to(ROOT).as_posix()


def _module_package(path: Path) -> tuple[str, ...]:
    """Return the package components containing a Python source file."""
    relative = path.relative_to(ROOT).with_suffix("")
    return relative.parts[:-1]


def _import_modules_from_tree(tree: ast.AST, package: tuple[str, ...]) -> set[str]:
    """Resolve effective imported modules, including relative ImportFrom aliases."""
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
    """Resolve imported module names from one repository Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return _import_modules_from_tree(tree, _module_package(path))


def _semantic_paths() -> list[Path]:
    """Enumerate the canonical semantic-control-plane Python surface."""
    paths = [GATEWAY]
    for directory in SEMANTIC_DIRS:
        paths.extend(sorted(directory.rglob("*.py")))
    return sorted({path for path in paths if path.is_file()})


def _is_moose_import(module: str) -> bool:
    """Return whether a module belongs to the local MOOSE adapter boundary."""
    return module == MOOSE_PREFIX or module.startswith(MOOSE_PREFIX + ".")


def _path_tokens(path: Path) -> set[str]:
    """Tokenize path components across separators, case, and known compounds."""
    tokens: set[str] = set()
    for part in path.parts:
        split_case = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", part)
        split_acronym = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", split_case)
        for token in re.split(r"[^a-z0-9]+", split_acronym.lower()):
            if not token:
                continue
            if token == "adapters":
                tokens.add("adapter")
            elif token == "jsonrpc":
                tokens.update(("json", "rpc"))
            else:
                tokens.add(token)
    return tokens


def _is_forbidden_local_owner(path: Path) -> bool:
    """Return whether a path names a SOL-runtime responsibility locally."""
    tokens = _path_tokens(path)
    return any(group <= tokens for group in FORBIDDEN_LOCAL_OWNER_TOKEN_GROUPS)


def _runtime_owner_paths() -> list[str]:
    """List Physics-local paths that duplicate SOL runtime ownership."""
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
    """Collect direct semantic-control-plane dependencies on local MOOSE code."""
    edges: set[tuple[str, str]] = set()
    for path in _semantic_paths():
        for module in _import_modules(path):
            if _is_moose_import(module):
                edges.add((_rel(path), MOOSE_PREFIX))
    return edges


def _identity_key(name: str) -> str:
    """Normalize identity spellings across case and separators."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _annotation_identifiers(node: ast.AST | None) -> set[str]:
    """Extract identity-bearing names from annotations, including forward refs."""
    if node is None:
        return set()
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            names.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", child.value))
    return names


def _state_target_names(node: ast.AST) -> set[str]:
    """Extract only ExecutionPlan instance-state names written by an assignment."""
    names: set[str] = set()
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
        names.add(node.attr)
    elif (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "self"
        and node.value.attr == "__dict__"
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
    ):
        names.add(node.slice.value)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for element in node.elts:
            names.update(_state_target_names(element))
    return names


def _expression_identifiers(node: ast.AST | None) -> set[str]:
    """Extract constructor/type identities referenced by an assigned expression."""
    if node is None:
        return set()
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


def _call_state_names(node: ast.Call) -> set[str]:
    """Extract dynamic state names from setattr(self, <name>, value)."""
    if (
        isinstance(node.func, ast.Name)
        and node.func.id == "setattr"
        and len(node.args) >= 2
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "self"
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    ):
        return {node.args[1].value}
    return set()


def _execution_plan_conflations_from_tree(tree: ast.Module) -> list[str]:
    """Reject SOL/MOOSE identity state anywhere on the ExecutionPlan class."""
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

    def inspect_assignment(
        targets: list[ast.AST], value: ast.AST | None, *, class_scope: bool = False
    ) -> None:
        state_names = {name for target in targets for name in _state_target_names(target)}
        for name in state_names:
            inspect(name)
        if class_scope:
            for target in targets:
                for name in _expression_identifiers(target):
                    inspect(name)
        if state_names or class_scope:
            for name in _expression_identifiers(value):
                inspect(name)

    for base in plan.bases:
        for name in _annotation_identifiers(base):
            inspect(name)

    for statement in plan.body:
        if isinstance(statement, ast.AnnAssign):
            inspect_assignment([statement.target], statement.value, class_scope=True)
            for name in _annotation_identifiers(statement.annotation):
                inspect(name)
        elif isinstance(statement, ast.Assign):
            inspect_assignment(list(statement.targets), statement.value, class_scope=True)
        elif isinstance(statement, ast.AugAssign):
            inspect_assignment([statement.target], statement.value, class_scope=True)
        elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in (*statement.args.posonlyargs, *statement.args.args, *statement.args.kwonlyargs):
                for name in _annotation_identifiers(arg.annotation):
                    inspect(name)
            if statement.args.vararg:
                for name in _annotation_identifiers(statement.args.vararg.annotation):
                    inspect(name)
            if statement.args.kwarg:
                for name in _annotation_identifiers(statement.args.kwarg.annotation):
                    inspect(name)
            for name in _annotation_identifiers(statement.returns):
                inspect(name)
            for child in ast.walk(statement):
                if isinstance(child, ast.AnnAssign):
                    inspect_assignment([child.target], child.value)
                    for name in _annotation_identifiers(child.annotation):
                        inspect(name)
                elif isinstance(child, ast.Assign):
                    inspect_assignment(list(child.targets), child.value)
                elif isinstance(child, ast.AugAssign):
                    inspect_assignment([child.target], child.value)
                elif isinstance(child, ast.NamedExpr):
                    inspect_assignment([child.target], child.value)
                elif isinstance(child, ast.Call):
                    state_names = _call_state_names(child)
                    for name in state_names:
                        inspect(name)
                    if state_names and len(child.args) >= 3:
                        for name in _expression_identifiers(child.args[2]):
                            inspect(name)
    return sorted(found)


def _execution_plan_conflations() -> list[str]:
    """Inspect the production ExecutionPlan declaration for forbidden identities."""
    path = HARNESS / "execution" / "plan.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return _execution_plan_conflations_from_tree(tree)


def _self_test() -> list[str]:
    """Mutation-test the boundary guard's own failure detectors."""
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
        "AdapterRuntime.py",
        "adapterRuntime.py",
        "JsonRpcTransport.py",
        "adapters/runtime.py",
        "jsonrpc_transport.py",
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
        "class ExecutionPlan(MappingPlan):\n"
        "    mapping_plan: int\n"
        "    realization_spec: \"RealizationSpec\"\n"
        "    payload = MappingPlan()\n"
        "    def __init__(self):\n"
        "        self.moose_target_ir = None\n"
        "        self.__dict__[\"adapter_protocol_version\"] = \"0.2\"\n"
        "    def attach(self, payload: \"MooseCaseIR\"):\n"
        "        self.public_contract_version = \"0.2\"\n"
        "        self.payload = MappingPlan()\n"
        "        setattr(self, \"realization_spec\", payload)\n"
    )
    conflations = _execution_plan_conflations_from_tree(synthetic_plan)
    for expected in (
        "MappingPlan",
        "mapping_plan",
        "realization_spec",
        "moose_target_ir",
        "adapter_protocol_version",
        "MooseCaseIR",
        "public_contract_version",
    ):
        if expected not in conflations:
            errors.append(f"self-test missed ExecutionPlan identity escape path: {expected}")
    class_scope_identity = ast.parse(
        "class ExecutionPlan:\n"
        "    payload = MappingPlan()\n"
    )
    if "MappingPlan" not in _execution_plan_conflations_from_tree(class_scope_identity):
        errors.append("self-test missed class-scope assigned MappingPlan identity")
    harmless_local = ast.parse(
        "class ExecutionPlan:\n"
        "    def attach(self):\n"
        "        mapping_plan = build()\n"
        "        return mapping_plan\n"
    )
    if _execution_plan_conflations_from_tree(harmless_local):
        errors.append("self-test treated method-local identity spelling as ExecutionPlan state")
    harmless_doc = ast.parse(
        "class ExecutionPlan:\n"
        "    \"\"\"ExecutionPlan is not a MappingPlan or RealizationSpec.\"\"\"\n"
        "    plan_id: str\n"
    )
    if _execution_plan_conflations_from_tree(harmless_doc):
        errors.append("self-test treated ExecutionPlan documentation as identity state")
    return errors


def _check() -> list[str]:
    """Evaluate current repository state against the frozen RFC invariants."""
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
    """Run guard self-tests and/or repository boundary checks."""
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