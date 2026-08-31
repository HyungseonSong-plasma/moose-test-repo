#!/usr/bin/env python3
"""P0 deletion gate for the historical Issue46 augmented-localization owner."""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LEGACY_MODULE = "qpx_harness.augmented_jacobian_localization"
LEGACY_PATH = ROOT / "qpx_harness" / "augmented_jacobian_localization.py"
SEMANTIC_PATH = ROOT / "qpx_harness" / "issue46_jacobian_localization.py"
FD_AUDIT_PATH = ROOT / "qpx_harness" / "jacobian_fd_reference_audit.py"
CLI_PATH = ROOT / "scripts" / "qpx.py"
PYTHON_ROOTS = ("qpx_harness", "recipes", "scripts", "tests", "performance")
EXECUTION_ROOTS = (".github", "tests", "performance")


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _static_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
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


def _dynamic_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    constants: dict[str, str] = {}
    for node in tree.body:
        value = getattr(node, "value", None)
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
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
                imports = _static_imports(path) | _dynamic_imports(path)
            except (OSError, UnicodeDecodeError, SyntaxError) as exc:
                raise RuntimeError(f"cannot inspect {path}: {exc}") from exc
            if LEGACY_MODULE in imports:
                consumers.append(str(path.relative_to(ROOT)))
    return sorted(consumers)


def _execution_consumers() -> list[str]:
    consumers: list[str] = []
    pattern = re.compile(
        r"python(?:3)?\s+-m\s+qpx_harness\.augmented_jacobian_localization\b"
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
            if pattern.search(source):
                consumers.append(str(path.relative_to(ROOT)))
    return sorted(consumers)


def _check_owner_boundary() -> None:
    if not LEGACY_PATH.is_file():
        raise AssertionError("legacy owner is already absent; use the post-retirement gate")
    if not SEMANTIC_PATH.is_file():
        raise AssertionError("canonical Issue46 semantic owner is missing")

    semantic_source = SEMANTIC_PATH.read_text()
    fd_source = FD_AUDIT_PATH.read_text()
    cli_source = CLI_PATH.read_text()
    for label, source in (
        ("semantic owner", semantic_source),
        ("FD audit", fd_source),
        ("CLI", cli_source),
    ):
        if "augmented_jacobian_localization" in source:
            raise AssertionError(f"{label} still contains legacy owner dependency")

    if "from qpx_harness.issue46_jacobian_localization import" not in cli_source:
        raise AssertionError("stable CLI is not bound to the semantic Issue46 owner")
    if "from . import issue46_jacobian_localization as localization_runtime" not in fd_source:
        raise AssertionError("FD audit is not bound to the semantic Issue46 owner")


def _negative_control() -> None:
    probe = ROOT / "tests" / "Issue48_qpx_harness_generality" / "_retirement_probe.py"
    source = (
        "import importlib\n"
        f"OWNER = {LEGACY_MODULE!r}\n"
        "module = importlib.import_module(OWNER)\n"
    )
    tree = ast.parse(source, filename=str(probe))
    constants = {
        node.targets[0].id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    detected = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "import_module"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and constants.get(node.args[0].id) == LEGACY_MODULE
        for node in ast.walk(tree)
    )
    if not detected:
        raise AssertionError("dynamic-import negative control failed")


def main() -> int:
    try:
        python_consumers = _python_consumers()
        if python_consumers:
            raise AssertionError(f"python consumers remain: {python_consumers}")
        print("ISSUE48_WP26_AUGMENTED_RETIREMENT_CHECK: python-consumers=ZERO")

        execution_consumers = _execution_consumers()
        if execution_consumers:
            raise AssertionError(f"execution consumers remain: {execution_consumers}")
        print("ISSUE48_WP26_AUGMENTED_RETIREMENT_CHECK: execution-consumers=ZERO")

        _check_owner_boundary()
        print("ISSUE48_WP26_AUGMENTED_RETIREMENT_CHECK: canonical-boundary=PASS")
        _negative_control()
        print("ISSUE48_WP26_AUGMENTED_RETIREMENT_CHECK: negative-control=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP26_AUGMENTED_RETIREMENT_CHARACTERIZATION: FAIL ({exc})")
        return 1

    print("ISSUE48_WP26_AUGMENTED_RETIREMENT_STATE: RETIREMENT_READY")
    print("ISSUE48_WP26_AUGMENTED_RETIREMENT_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
