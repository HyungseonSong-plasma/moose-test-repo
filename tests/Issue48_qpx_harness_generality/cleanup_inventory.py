#!/usr/bin/env python3
"""Issue48 cleanup inventory for legacy qpx_harness owners.

This checker answers one narrow question before deletion: which mixed/legacy
modules still have executable consumers in repository Python or CI/test command
surfaces?  It does not delete anything and does not classify scientific state.
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
    "coupling_evr1",
    "coupling_evr1_safe",
    "coupling_evr2_timestep",
    "dmix_equivalence",
    "dmix_equivalence_structured",
    "electron_inventory_nullspace",
    "fast_plasma_coupling_diagnostic",
    "fast_plasma_relaxation",
    "fast_plasma_relaxation_v2",
    "fast_plasma_relaxation_v3",
    "fast_plasma_relaxation_v4",
    "fast_plasma_relaxation_v5",
    "jacobian_fd_reference_audit",
    "petsc_first_linear_diagnostic",
    "performance_cache_audit",
    "performance_core",
    "performance_investigation",
    "performance_smoke",
    "performance_transport_probe",
    "performance_transport_probe_direct",
    "performance_transport_probe_resilient",
    "scale_audit",
)

PYTHON_SCAN_ROOTS = (
    "qpx_harness",
    "recipes",
    "scripts",
    "tests",
    "performance",
)

EXECUTION_SCAN_ROOTS = (
    ".github",
    "tests",
    "performance",
)


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
    if path.name == "__init__.py":
        return module
    return module.rpartition(".")[0]


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

    imports: list[str] = []
    if base:
        imports.append(base)

    # ``from package import name`` can import a package attribute or a real
    # submodule.  For deletion safety conservatively treat ``package.name`` as
    # a module consumer as well.  This catches shapes such as:
    #
    #   from qpx_harness import jacobian_fd_reference_audit as legacy
    #
    # while the top-level candidate reduction below prevents attributes
    # imported from deeper modules from creating unrelated candidate edges.
    for alias in node.names:
        if alias.name == "*":
            continue
        imported = f"{base}.{alias.name}" if base else alias.name
        imports.append(imported)
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
            if "__pycache__" in path.parts:
                continue
            yield path


def _top_qpx_module(name: str) -> str | None:
    prefix = "qpx_harness."
    if not name.startswith(prefix):
        return None
    tail = name[len(prefix) :]
    if not tail:
        return None
    return tail.split(".", 1)[0]


def python_consumers(root: Path = ROOT) -> dict[str, set[str]]:
    consumers: dict[str, set[str]] = defaultdict(set)
    for path in _iter_python_files(root):
        module = _module_name(path, root)
        if not module:
            continue
        try:
            source = path.read_text()
            imports = imported_modules(source, module_name=module, path=path)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            raise RuntimeError(f"cannot inspect {path}: {exc}") from exc
        for imported in imports:
            top = _top_qpx_module(imported)
            if top and top in CLEANUP_CANDIDATES:
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
    """Separate live/runtime consumers from characterization/test consumers."""
    runtime: list[str] = []
    tests: list[str] = []
    for consumer in sorted(set(consumers)):
        if consumer.startswith("tests/"):
            tests.append(consumer)
        else:
            runtime.append(consumer)
    return runtime, tests


def inventory(root: Path = ROOT) -> dict[str, object]:
    scripts_dir = root / "scripts"
    script_files = sorted(
        str(path.relative_to(root)) for path in scripts_dir.iterdir() if path.is_file()
    )
    expected_scripts = ["scripts/qpx.py"]

    py = python_consumers(root)
    execution = execution_consumers(root)
    candidates: dict[str, dict[str, object]] = {}
    zero: list[str] = []
    test_only: list[str] = []
    runtime_blocked: list[str] = []
    for module in CLEANUP_CANDIDATES:
        all_consumers = sorted(py.get(module, set()) | execution.get(module, set()))
        runtime_consumers, test_consumers = _partition_consumers(all_consumers)
        if not all_consumers:
            status = "ZERO_CONSUMER"
            zero.append(module)
        elif runtime_consumers:
            status = "BLOCKED_RUNTIME"
            runtime_blocked.append(module)
        else:
            status = "TEST_ONLY"
            test_only.append(module)
        candidates[module] = {
            "status": status,
            "consumers": all_consumers,
            "runtime_consumers": runtime_consumers,
            "test_consumers": test_consumers,
            "python_consumers": sorted(py.get(module, set())),
            "execution_consumers": sorted(execution.get(module, set())),
        }

    return {
        "scripts_status": "PASS" if script_files == expected_scripts else "HOLD",
        "scripts": script_files,
        "expected_scripts": expected_scripts,
        "candidates": candidates,
        "zero_consumer_candidates": zero,
        "test_only_candidates": test_only,
        "runtime_blocked_candidates": runtime_blocked,
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
            source,
            module_name="qpx_harness.example",
            path=path,
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

        # Regression control for the exact false-ZERO_CONSUMER shape that the
        # cleanup gate must not miss.
        compat_source = (
            "from qpx_harness import jacobian_fd_reference_audit as legacy\n"
        )
        compat_imports = imported_modules(
            compat_source,
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

        # This must be syntactically invalid Python.  The previous control
        # ``this is not python`` was actually a valid ``is not`` expression.
        bad_source = "def broken(:\n    pass\n"
        try:
            imported_modules(
                bad_source,
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

    result = inventory()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "ISSUE48_CLEANUP_SCRIPTS:",
            result["scripts_status"],
            "files=" + ",".join(result["scripts"]),
        )
        candidates = result["candidates"]
        for module in CLEANUP_CANDIDATES:
            item = candidates[module]
            runtime = item["runtime_consumers"]
            tests = item["test_consumers"]
            runtime_suffix = ",".join(runtime) if runtime else "NONE"
            test_suffix = ",".join(tests) if tests else "NONE"
            print(
                f"ISSUE48_CLEANUP_CANDIDATE: {module} "
                f"status={item['status']} "
                f"runtime_consumers={runtime_suffix} "
                f"test_consumers={test_suffix}"
            )
        print(
            "ISSUE48_CLEANUP_RUNTIME_BLOCKED_COUNT:",
            len(result["runtime_blocked_candidates"]),
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
