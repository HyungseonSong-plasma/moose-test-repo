#!/usr/bin/env python3
"""P0 post-retirement gate for the historical Issue46 FD proxy."""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LEGACY_MODULE = "qpx_harness.jacobian_fd_reference_audit"
SEMANTIC_MODULE = "qpx_harness.issue46_fd_reference"
LEGACY_PATH = ROOT / "qpx_harness" / "jacobian_fd_reference_audit.py"
SEMANTIC_PATH = ROOT / "qpx_harness" / "issue46_fd_reference.py"
PYTHON_ROOTS = ("qpx_harness", "recipes", "scripts", "tests", "performance")
EXECUTION_ROOTS = (".github", "tests", "performance")


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _resolved_static_imports_source(source: str, *, path: Path) -> set[str]:
    tree = ast.parse(source, filename=str(path))
    module = _module_name(path)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                try:
                    base = importlib.util.resolve_name(
                        "." * node.level + (node.module or ""), package
                    )
                except (ImportError, ValueError):
                    continue
            else:
                base = node.module or ""
            if base:
                result.add(base)
            for alias in node.names:
                if alias.name != "*":
                    result.add(f"{base}.{alias.name}" if base else alias.name)
    return result


def _dynamic_imports_source(source: str, *, path: Path) -> set[str]:
    tree = ast.parse(source, filename=str(path))
    constants: dict[str, str] = {}
    for node in tree.body:
        value = getattr(node, "value", None)
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        for target in targets:
            if isinstance(target, ast.Name):
                constants[target.id] = value.value

    result: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        is_dynamic_import = (
            isinstance(func, ast.Name) and func.id in {"import_module", "__import__"}
        ) or (
            isinstance(func, ast.Attribute)
            and func.attr == "import_module"
            and isinstance(func.value, ast.Name)
            and func.value.id == "importlib"
        )
        if not is_dynamic_import:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            result.add(arg.value)
        elif isinstance(arg, ast.Name) and arg.id in constants:
            result.add(constants[arg.id])
    return result


def _python_consumers() -> list[str]:
    consumers: list[str] = []
    for rel_root in PYTHON_ROOTS:
        base = ROOT / rel_root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if path == LEGACY_PATH or "__pycache__" in path.parts:
                continue
            try:
                source = path.read_text()
                imports = _resolved_static_imports_source(source, path=path)
                imports |= _dynamic_imports_source(source, path=path)
            except (OSError, UnicodeDecodeError, SyntaxError) as exc:
                raise RuntimeError(f"cannot inspect {path}: {exc}") from exc
            if LEGACY_MODULE in imports:
                consumers.append(str(path.relative_to(ROOT)))
    return sorted(consumers)


def _execution_consumers() -> list[str]:
    consumers: list[str] = []
    module_pattern = re.compile(
        r"python(?:3)?\s+-m\s+qpx_harness\.jacobian_fd_reference_audit\b"
    )
    path_pattern = re.compile(
        r"python(?:3)?\s+qpx_harness/jacobian_fd_reference_audit\.py\b"
    )
    suffixes = {".yml", ".yaml", ".sh", ".toml", ".json"}
    for rel_root in EXECUTION_ROOTS:
        base = ROOT / rel_root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            try:
                source = path.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            if module_pattern.search(source) or path_pattern.search(source):
                consumers.append(str(path.relative_to(ROOT)))
    return sorted(consumers)


def _check_owner_absent() -> None:
    if LEGACY_PATH.exists():
        raise AssertionError("retired historical FD proxy unexpectedly exists")


def _check_canonical_boundary() -> None:
    if not SEMANTIC_PATH.is_file():
        raise AssertionError("canonical Issue46 FD semantic owner is missing")

    semantic_source = SEMANTIC_PATH.read_text()
    semantic_imports = _resolved_static_imports_source(semantic_source, path=SEMANTIC_PATH)
    if LEGACY_MODULE in semantic_imports:
        raise AssertionError("semantic FD owner reverse-depends on the retired historical proxy")
    if "recipes.issue46_fd_reference" not in semantic_imports:
        raise AssertionError("semantic FD owner lost its recipe composition boundary")


def _negative_control() -> None:
    probe = ROOT / "tests" / "Issue48_qpx_harness_generality" / "_legacy_fd_probe.py"

    static_source = "from qpx_harness import jacobian_fd_reference_audit as legacy\n"
    if LEGACY_MODULE not in _resolved_static_imports_source(static_source, path=probe):
        raise AssertionError("static-import negative control failed")

    dynamic_source = (
        "import importlib\n"
        f"OWNER = {LEGACY_MODULE!r}\n"
        "module = importlib.import_module(OWNER)\n"
    )
    if LEGACY_MODULE not in _dynamic_imports_source(dynamic_source, path=probe):
        raise AssertionError("dynamic-import negative control failed")

    module_cmd = "python3 -m qpx_harness.jacobian_fd_reference_audit --self-test"
    path_cmd = "python3 qpx_harness/jacobian_fd_reference_audit.py --self-test"
    if not re.search(
        r"python(?:3)?\s+-m\s+qpx_harness\.jacobian_fd_reference_audit\b",
        module_cmd,
    ):
        raise AssertionError("module-execution negative control failed")
    if not re.search(
        r"python(?:3)?\s+qpx_harness/jacobian_fd_reference_audit\.py\b",
        path_cmd,
    ):
        raise AssertionError("path-execution negative control failed")


def main() -> int:
    try:
        _check_owner_absent()
        print("ISSUE48_WP29_ISSUE46_FD_LEGACY_RETIREMENT_CHECK: owner-absent=PASS")

        python_consumers = _python_consumers()
        if python_consumers:
            raise AssertionError(f"python consumers remain: {python_consumers}")
        print("ISSUE48_WP29_ISSUE46_FD_LEGACY_RETIREMENT_CHECK: python-consumers=ZERO")

        execution_consumers = _execution_consumers()
        if execution_consumers:
            raise AssertionError(f"execution consumers remain: {execution_consumers}")
        print("ISSUE48_WP29_ISSUE46_FD_LEGACY_RETIREMENT_CHECK: execution-consumers=ZERO")

        _check_canonical_boundary()
        print("ISSUE48_WP29_ISSUE46_FD_LEGACY_RETIREMENT_CHECK: canonical-boundary=PASS")
        _negative_control()
        print("ISSUE48_WP29_ISSUE46_FD_LEGACY_RETIREMENT_CHECK: negative-control=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP29_ISSUE46_FD_LEGACY_RETIREMENT_CHARACTERIZATION: FAIL ({exc})")
        return 1

    print("ISSUE48_WP29_ISSUE46_FD_LEGACY_RETIREMENT_STATE: RETIRED")
    print("ISSUE48_WP29_ISSUE46_FD_LEGACY_RETIREMENT_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
