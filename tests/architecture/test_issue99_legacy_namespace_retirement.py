from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIVE_ROOTS = ("qpx_harness", "tests", "experiments", "recipes", "tools")
LEGACY_PACKAGES = ("qpx_harness.evidence_engine", "qpx_harness.diagnostics")
LEGACY_DIRS = (
    REPO_ROOT / "qpx_harness" / "evidence_engine",
    REPO_ROOT / "qpx_harness" / "diagnostics",
)


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _legacy_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(LEGACY_PACKAGES):
                    hits.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 0 and module.startswith(LEGACY_PACKAGES):
                hits.append(f"from {module} import ...")
            elif (
                path.is_relative_to(REPO_ROOT / "qpx_harness")
                and node.level > 0
                and (module == "diagnostics" or module.startswith("diagnostics.") or module == "evidence_engine" or module.startswith("evidence_engine."))
            ):
                hits.append(f"relative legacy import level={node.level} module={module}")
    return hits


def test_no_active_code_imports_transitional_evidence_engine_or_diagnostics() -> None:
    violations: list[str] = []
    for root_name in ACTIVE_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if path == Path(__file__).resolve():
                continue
            if any(_is_under(path, legacy_dir) for legacy_dir in LEGACY_DIRS):
                continue
            for hit in _legacy_imports(path):
                violations.append(f"{path.relative_to(REPO_ROOT)}: {hit}")

    assert not violations, "legacy namespace imports remain:\n" + "\n".join(violations)
