from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_NAMESPACE = "qpx_harness.dmix"
LEGACY_DIR = REPO_ROOT / "qpx_harness" / "dmix"
SCAN_ROOTS = ("qpx_harness", "tests", "experiments", "recipes", "bin", "tools")


def _legacy_references(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == LEGACY_NAMESPACE or alias.name.startswith(LEGACY_NAMESPACE + "."):
                    hits.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            module = node.module or ""
            if module == LEGACY_NAMESPACE or module.startswith(LEGACY_NAMESPACE + "."):
                hits.append(f"from {module} import ...")
        elif isinstance(node, ast.Call) and node.args:
            first = node.args[0]
            if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                continue
            is_builtin_import = isinstance(node.func, ast.Name) and node.func.id == "__import__"
            is_importlib = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "importlib"
            )
            if (is_builtin_import or is_importlib) and (
                first.value == LEGACY_NAMESPACE or first.value.startswith(LEGACY_NAMESPACE + ".")
            ):
                hits.append(f"dynamic import {first.value}")
    return hits


def test_dmix_namespace_is_physically_retired() -> None:
    assert not LEGACY_DIR.exists(), "qpx_harness/dmix must remain physically retired"


def test_no_active_code_imports_retired_dmix_namespace() -> None:
    violations: list[str] = []
    this_file = Path(__file__).resolve()
    for root_name in SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if path.resolve() == this_file:
                continue
            for hit in _legacy_references(path):
                violations.append(f"{path.relative_to(REPO_ROOT)}: {hit}")
    assert not violations, "retired dmix imports remain:\n" + "\n".join(violations)
