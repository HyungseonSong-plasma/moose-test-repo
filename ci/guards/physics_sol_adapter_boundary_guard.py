#!/usr/bin/env python3
"""Guard the Physics semantic control plane after the #280 SOL cutover."""
from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "physics_harness"
GATEWAY = HARNESS / "application" / "gateway.py"
SEMANTIC_DIRS = (HARNESS / "specification", HARNESS / "planning", HARNESS / "execution", HARNESS / "ontology")
MOOSE_PREFIX = "physics_harness.adapters.moose"
FORBIDDEN_LOCAL_OWNER_TOKEN_GROUPS = (
    frozenset({"adapter", "runtime"}), frozenset({"adapter", "transport"}),
    frozenset({"adapter", "registry"}), frozenset({"adapter", "session"}),
    frozenset({"json", "rpc", "transport"}), frozenset({"process", "lifecycle"}),
    frozenset({"session", "lifecycle"}), frozenset({"adapter", "compatibility"}),
    frozenset({"adapter", "selector"}), frozenset({"response", "loss"}),
)
FORBIDDEN_EXECUTION_PLAN_IDENTITIES = {
    "MooseTargetIR", "MooseCaseIR", "MappingPlan", "RealizationSpec",
    "adapter_protocol_version", "public_contract_version",
}


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


FORBIDDEN_KEYS = {_key(value) for value in FORBIDDEN_EXECUTION_PLAN_IDENTITIES}


def _tokens(path: Path) -> set[str]:
    out: set[str] = set()
    for part in path.parts:
        part = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", part)
        for token in re.split(r"[^a-z0-9]+", part.lower()):
            if token == "adapters":
                token = "adapter"
            if token == "jsonrpc":
                out.update(("json", "rpc"))
                continue
            if token:
                out.add(token)
    return out


def _runtime_owner_paths() -> list[str]:
    found = []
    for path in HARNESS.rglob("*"):
        if "__pycache__" in path.parts:
            continue
        tokens = _tokens(path)
        if any(group <= tokens for group in FORBIDDEN_LOCAL_OWNER_TOKEN_GROUPS):
            found.append(path.relative_to(ROOT).as_posix() + ("/" if path.is_dir() else ""))
    return sorted(set(found))


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
    violations = []
    for path in _semantic_paths():
        for module in _imports(path):
            if module == MOOSE_PREFIX or module.startswith(MOOSE_PREFIX + "."):
                violations.append(f"{path.relative_to(ROOT).as_posix()} -> {module}")
    return sorted(set(violations))


def _identifiers(node: ast.AST | None) -> set[str]:
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


def _execution_plan_conflations_from_tree(tree: ast.Module) -> list[str]:
    plan = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ExecutionPlan"), None)
    if plan is None:
        return ["ExecutionPlan<missing>"]
    found: set[str] = set()

    def inspect(name: str) -> None:
        if _key(name) in FORBIDDEN_KEYS:
            found.add(name)

    for base in plan.bases:
        for name in _identifiers(base):
            inspect(name)
    for statement in plan.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            inspect(statement.target.id)
        elif isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    inspect(target.id)
    for node in ast.walk(plan):
        if isinstance(node, ast.AnnAssign):
            for name in _identifiers(node.annotation):
                inspect(name)
            if isinstance(node.target, ast.Attribute) and isinstance(node.target.value, ast.Name) and node.target.value.id == "self":
                inspect(node.target.attr)
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                    inspect(target.attr)
                if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Attribute) and target.value.attr == "__dict__" and isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
                    inspect(target.slice.value)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "setattr" and len(node.args) >= 2 and isinstance(node.args[0], ast.Name) and node.args[0].id == "self" and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
            inspect(node.args[1].value)
    return sorted(found)


def _execution_plan_conflations() -> list[str]:
    path = HARNESS / "execution" / "plan.py"
    return _execution_plan_conflations_from_tree(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))


def _self_test() -> list[str]:
    errors: list[str] = []
    synthetic = ast.parse('class ExecutionPlan(MappingPlan):\n    mapping_plan: object | None = None\n    def f(self):\n        self.moose_target_ir = None\n        self.__dict__["adapter_protocol_version"] = "0.2"\n        setattr(self, "realization_spec", None)\n')
    found = set(_execution_plan_conflations_from_tree(synthetic))
    for expected in {"MappingPlan", "mapping_plan", "moose_target_ir", "adapter_protocol_version", "realization_spec"}:
        if expected not in found:
            errors.append(f"self-test missed identity escape path: {expected}")
    for name in ("adapter_runtime.py", "json_rpc_transport.py", "adapter_registry.py", "process_lifecycle.py"):
        tokens = _tokens(Path(name))
        if not any(group <= tokens for group in FORBIDDEN_LOCAL_OWNER_TOKEN_GROUPS):
            errors.append(f"self-test missed runtime owner: {name}")
    return errors


def _check() -> list[str]:
    errors: list[str] = []
    owners = _runtime_owner_paths()
    if owners:
        errors.append("Physics-local SOL runtime ownership is forbidden: " + ", ".join(owners))
    edges = _semantic_moose_edges()
    if edges:
        errors.append("semantic control-plane direct MOOSE edges must be zero: " + ", ".join(edges))
    conflations = _execution_plan_conflations()
    if conflations:
        errors.append("ExecutionPlan must not absorb SOL/MOOSE contract identities: " + ", ".join(conflations))
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
        for error in errors:
            print(f"PHYSICS_SOL_ADAPTER_BOUNDARY_GUARD: FAIL: {error}")
        return 1
    if args.self_test:
        print("PHYSICS_SOL_ADAPTER_BOUNDARY_GUARD_SELF_TEST: PASS")
    if args.check:
        print("PHYSICS_SOL_ADAPTER_BOUNDARY_GUARD: PASS")
        print("DIRECT_APPLICATION_TO_LOCAL_MOOSE_IMPLEMENTATION=0")
        print("PHYSICS_LOCAL_ADAPTER_RUNTIME_OWNER_COUNT=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
