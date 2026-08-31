#!/usr/bin/env python3
"""Issue48 cleanup inventory for legacy qpx_harness owners.

The checker answers one deletion-safety question: which remaining legacy or
mixed-owner modules still have executable or characterization consumers? It is
read-only and does not classify scientific state.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]

CLEANUP_CANDIDATES = (
    "augmented_jacobian_localization",
    "electron_inventory_nullspace",
    "fast_plasma_coupling_diagnostic",
    "jacobian_fd_reference_audit",
    "scale_audit",
)

PYTHON_SCAN_ROOTS = ("qpx_harness", "recipes", "scripts", "tests", "performance")
EXECUTION_SCAN_ROOTS = (".github", "tests", "performance")


def _module_name(path: Path, root: Path = ROOT) -> str | None:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    if rel.suffix != ".py":
        return None
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else None


def _package_for(module: str, path: Path) -> str:
    return module if path.name == "__init__.py" else module.rpartition(".")[0]


def _resolve_from_import(
    *, module_name: str, path: Path, node: ast.ImportFrom
) -> list[str]:
    package = _package_for(module_name, path)
    if node.level:
        relative = "." * node.level + (node.module or "")
        try:
            base = importlib.util.resolve_name(relative, package)
        except (ImportError, ValueError):
            return []
    else:
        base = node.module or ""

    imports: list[str] = [base] if base else []
    for alias in node.names:
        if alias.name == "*":
            continue
        imports.append(f"{base}.{alias.name}" if base else alias.name)
    return imports


def imported_modules(source: str, *, module_name: str, path: Path) -> set[str]:
    tree = ast.parse(source, filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result.update(
                _resolve_from_import(module_name=module_name, path=path, node=node)
            )
    return result


def _iter_python_files(root: Path = ROOT) -> Iterable[Path]:
    for rel in PYTHON_SCAN_ROOTS:
        base = root / rel
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" not in path.parts:
                yield path


def _top_qpx_module(name: str) -> str | None:
    prefix = "qpx_harness."
    if not name.startswith(prefix):
        return None
    tail = name[len(prefix) :]
    return tail.split(".", 1)[0] if tail else None


def python_consumers(root: Path = ROOT) -> dict[str, set[str]]:
    consumers: dict[str, set[str]] = defaultdict(set)
    for path in _iter_python_files(root):
        module = _module_name(path, root)
        if not module:
            continue
        try:
            imports = imported_modules(
                path.read_text(), module_name=module, path=path
            )
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            raise RuntimeError(f"cannot inspect {path}: {exc}") from exc
        for imported in imports:
            top = _top_qpx_module(imported)
            if top in CLEANUP_CANDIDATES:
                consumers[top].add(str(path.relative_to(root)))
    return consumers


def execution_consumers(root: Path = ROOT) -> dict[str, set[str]]:
    consumers: dict[str, set[str]] = defaultdict(set)
    pattern = re.compile(
        r"(?:python(?:3)?\s+-m\s+)(?:qpx_harness\.)([A-Za-z_][A-Za-z0-9_]*)"
    )
    suffixes = {".yml", ".yaml", ".sh", ".toml", ".json"}
    for rel in EXECUTION_SCAN_ROOTS:
        base = root / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            try:
                text = path.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            for match in pattern.finditer(text):
                module = match.group(1)
                if module in CLEANUP_CANDIDATES:
                    consumers[module].add(str(path.relative_to(root)))
    return consumers


def _partition_consumers(consumers: Iterable[str]) -> tuple[list[str], list[str]]:
    runtime: list[str] = []
    tests: list[str] = []
    for consumer in sorted(set(consumers)):
        (tests if consumer.startswith("tests/") else runtime).append(consumer)
    return runtime, tests


def _partition_runtime_consumers(
    runtime_consumers: Iterable[str],
) -> tuple[list[str], list[str]]:
    internal: list[str] = []
    entrypoints: list[str] = []
    for consumer in sorted(set(runtime_consumers)):
        (internal if consumer.startswith("qpx_harness/") else entrypoints).append(
            consumer
        )
    return internal, entrypoints


def _collapse_role(
    *,
    status: str,
    internal_runtime: list[str],
    entrypoint_runtime: list[str],
    tests: list[str],
) -> str:
    if status == "ZERO_CONSUMER":
        return "ZERO_CONSUMER"
    if status == "TEST_ONLY":
        return "TEST_ONLY"
    if entrypoint_runtime:
        return "ENTRYPOINT_BOUND"
    if tests:
        return "INTERNAL_PLUS_TESTS"
    if len(internal_runtime) == 1:
        return "SINGLE_INTERNAL_CONSUMER"
    return "INTERNAL_ONLY"


def inventory(root: Path = ROOT) -> dict[str, object]:
    scripts = sorted(
        str(path.relative_to(root))
        for path in (root / "scripts").iterdir()
        if path.is_file()
    )
    py = python_consumers(root)
    execution = execution_consumers(root)
    candidates: dict[str, dict[str, object]] = {}
    zero: list[str] = []
    test_only: list[str] = []
    runtime_blocked: list[str] = []
    internal_only: list[str] = []
    single_internal: list[str] = []

    for module in CLEANUP_CANDIDATES:
        path = root / "qpx_harness" / f"{module}.py"
        if not path.is_file():
            raise RuntimeError(
                f"cleanup candidate does not exist; remove retired owner from catalog: {path}"
            )
        all_consumers = sorted(py.get(module, set()) | execution.get(module, set()))
        runtime, tests = _partition_consumers(all_consumers)
        internal_runtime, entrypoint_runtime = _partition_runtime_consumers(runtime)
        if not all_consumers:
            status = "ZERO_CONSUMER"
            zero.append(module)
        elif runtime:
            status = "BLOCKED_RUNTIME"
            runtime_blocked.append(module)
        else:
            status = "TEST_ONLY"
            test_only.append(module)

        collapse_role = _collapse_role(
            status=status,
            internal_runtime=internal_runtime,
            entrypoint_runtime=entrypoint_runtime,
            tests=tests,
        )
        if collapse_role in {"INTERNAL_ONLY", "SINGLE_INTERNAL_CONSUMER"}:
            internal_only.append(module)
        if collapse_role == "SINGLE_INTERNAL_CONSUMER":
            single_internal.append(module)

        candidates[module] = {
            "status": status,
            "collapse_role": collapse_role,
            "runtime_consumers": runtime,
            "internal_runtime_consumers": internal_runtime,
            "entrypoint_runtime_consumers": entrypoint_runtime,
            "test_consumers": tests,
        }

    return {
        "scripts_status": "PASS" if scripts == ["scripts/qpx.py"] else "HOLD",
        "scripts": scripts,
        "candidates": candidates,
        "zero_consumer_candidates": zero,
        "test_only_candidates": test_only,
        "runtime_blocked_candidates": runtime_blocked,
        "internal_only_candidates": internal_only,
        "single_internal_consumer_candidates": single_internal,
    }


def self_test() -> int:
    try:
        path = ROOT / "qpx_harness" / "example.py"
        source = (
            "from . import sibling as s\n"
            "from qpx_harness import gamma as g\n"
            "from qpx_harness.alpha import main\n"
            "import qpx_harness.beta\n"
            "text = 'qpx_harness.not_an_import'\n"
        )
        imports = imported_modules(
            source, module_name="qpx_harness.example", path=path
        )
        required = {
            "qpx_harness.sibling",
            "qpx_harness.gamma",
            "qpx_harness.alpha",
            "qpx_harness.beta",
        }
        if not required.issubset(imports):
            raise AssertionError(f"missing imports: {required - imports}")
        if "qpx_harness.not_an_import" in imports:
            raise AssertionError("string literal was misclassified as import")

        compat_imports = imported_modules(
            "from qpx_harness import jacobian_fd_reference_audit as legacy\n",
            module_name="qpx_harness.compat.example",
            path=ROOT / "qpx_harness" / "compat" / "example.py",
        )
        if "qpx_harness.jacobian_fd_reference_audit" not in compat_imports:
            raise AssertionError("package submodule import consumer was not detected")

        runtime, tests = _partition_consumers(
            {
                "qpx_harness/legacy.py",
                "scripts/qpx.py",
                "tests/Issue48/example.py",
            }
        )
        if runtime != ["qpx_harness/legacy.py", "scripts/qpx.py"]:
            raise AssertionError(f"runtime consumer partition drift: {runtime}")
        if tests != ["tests/Issue48/example.py"]:
            raise AssertionError(f"test consumer partition drift: {tests}")

        internal, entrypoints = _partition_runtime_consumers(runtime)
        if internal != ["qpx_harness/legacy.py"]:
            raise AssertionError(f"internal consumer partition drift: {internal}")
        if entrypoints != ["scripts/qpx.py"]:
            raise AssertionError(f"entrypoint consumer partition drift: {entrypoints}")
        if (
            _collapse_role(
                status="BLOCKED_RUNTIME",
                internal_runtime=["qpx_harness/next.py"],
                entrypoint_runtime=[],
                tests=[],
            )
            != "SINGLE_INTERNAL_CONSUMER"
        ):
            raise AssertionError("single-internal collapse role was not detected")
        if (
            _collapse_role(
                status="BLOCKED_RUNTIME",
                internal_runtime=["qpx_harness/next.py"],
                entrypoint_runtime=["scripts/qpx.py"],
                tests=[],
            )
            != "ENTRYPOINT_BOUND"
        ):
            raise AssertionError("entrypoint-bound collapse role was not detected")

        try:
            imported_modules(
                "def broken(:\n    pass\n",
                module_name="qpx_harness.example",
                path=path,
            )
        except SyntaxError:
            pass
        else:
            raise AssertionError("syntax-error negative control was accepted")
    except Exception as exc:
        print(f"ISSUE48_CLEANUP_INVENTORY_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_CLEANUP_INVENTORY_SELFTEST: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()

    try:
        result = inventory()
    except Exception as exc:
        print(f"ISSUE48_CLEANUP_INVENTORY: FAIL ({exc})")
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "ISSUE48_CLEANUP_SCRIPTS:",
            result["scripts_status"],
            "files=" + ",".join(result["scripts"]),
        )
        for module in CLEANUP_CANDIDATES:
            item = result["candidates"][module]
            runtime = item["runtime_consumers"]
            internal_runtime = item["internal_runtime_consumers"]
            entrypoint_runtime = item["entrypoint_runtime_consumers"]
            tests = item["test_consumers"]
            print(
                f"ISSUE48_CLEANUP_CANDIDATE: {module} "
                f"status={item['status']} "
                f"collapse_role={item['collapse_role']} "
                f"runtime_consumers={','.join(runtime) if runtime else 'NONE'} "
                f"internal_runtime_consumers={','.join(internal_runtime) if internal_runtime else 'NONE'} "
                f"entrypoint_runtime_consumers={','.join(entrypoint_runtime) if entrypoint_runtime else 'NONE'} "
                f"test_consumers={','.join(tests) if tests else 'NONE'}"
            )
        print(
            "ISSUE48_CLEANUP_RUNTIME_BLOCKED_COUNT:",
            len(result["runtime_blocked_candidates"]),
        )
        print(
            "ISSUE48_CLEANUP_INTERNAL_ONLY_COUNT:",
            len(result["internal_only_candidates"]),
        )
        if result["internal_only_candidates"]:
            print(
                "ISSUE48_CLEANUP_INTERNAL_ONLY:",
                ",".join(result["internal_only_candidates"]),
            )
        print(
            "ISSUE48_CLEANUP_SINGLE_INTERNAL_CONSUMER_COUNT:",
            len(result["single_internal_consumer_candidates"]),
        )
        if result["single_internal_consumer_candidates"]:
            print(
                "ISSUE48_CLEANUP_SINGLE_INTERNAL_CONSUMERS:",
                ",".join(result["single_internal_consumer_candidates"]),
            )
        print(
            "ISSUE48_CLEANUP_TEST_ONLY_COUNT:",
            len(result["test_only_candidates"]),
        )
        if result["test_only_candidates"]:
            print(
                "ISSUE48_CLEANUP_TEST_ONLY:",
                ",".join(result["test_only_candidates"]),
            )
        print(
            "ISSUE48_CLEANUP_ZERO_CONSUMER_COUNT:",
            len(result["zero_consumer_candidates"]),
        )
        if result["zero_consumer_candidates"]:
            print(
                "ISSUE48_CLEANUP_ZERO_CONSUMERS:",
                ",".join(result["zero_consumer_candidates"]),
            )

    ok = result["scripts_status"] == "PASS"
    print("ISSUE48_CLEANUP_INVENTORY:", "PASS" if ok else "HOLD")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
