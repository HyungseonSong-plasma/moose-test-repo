#!/usr/bin/env python3
"""P0 retirement characterization for the historical Issue45 first-linear owner.

This checker is valid both immediately before and after retirement. Before
retirement it requires zero static consumers; after retirement it requires the
historical owner to remain absent. In both states it verifies the canonical
semantic/runtime and recipe ownership surfaces and the stable CLI route.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import issue45_first_linear as semantic
from recipes import issue45_first_linear as recipe

LEGACY_MODULE = "qpx_harness.petsc_first_linear_diagnostic"
LEGACY = ROOT / "qpx_harness" / "petsc_first_linear_diagnostic.py"
SEMANTIC = ROOT / "qpx_harness" / "issue45_first_linear.py"
CLI = ROOT / "scripts" / "qpx.py"


def _imports_module(path: Path, module_name: str) -> bool:
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == module_name for alias in node.names):
                return True
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
            if base == module_name:
                return True
            parent, _, child = module_name.rpartition(".")
            if base == parent and any(alias.name == child for alias in node.names):
                return True
    return False


def _legacy_consumers() -> list[str]:
    consumers: list[str] = []
    for rel_root in ("qpx_harness", "recipes", "scripts", "tests", "performance"):
        base = ROOT / rel_root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if path == LEGACY:
                continue
            try:
                if _imports_module(path, LEGACY_MODULE):
                    consumers.append(str(path.relative_to(ROOT)))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
    return sorted(consumers)


def _check_zero_consumer_or_retired() -> str:
    consumers = _legacy_consumers()
    if consumers:
        raise AssertionError(f"legacy first-linear consumers remain: {consumers}")
    return "READY" if LEGACY.is_file() else "RETIRED"


def _check_canonical_owners() -> None:
    if not SEMANTIC.is_file():
        raise AssertionError("semantic Issue45 first-linear runtime owner missing")
    for name in (
        "ISSUE",
        "TARGET",
        "DIAGNOSTIC_NL_MAX_ITS",
        "JACOBIAN_REL_TOL",
        "FIRST_LINEAR_PETSC_OPTIONS",
        "REQUIRED_EXISTING_OPTIONS",
    ):
        if getattr(semantic, name) != getattr(recipe, name):
            raise AssertionError(f"semantic/recipe policy identity drift: {name}")
    if semantic.instrument_first_linear is not recipe.instrument_first_linear:
        raise AssertionError("semantic instrumentation is not canonical recipe alias")
    if semantic.analyze_first_linear_text is not recipe.analyze_first_linear_text:
        raise AssertionError("semantic analysis is not canonical recipe alias")

    semantic_source = SEMANTIC.read_text()
    if "petsc_first_linear_diagnostic" in semantic_source:
        raise AssertionError("semantic owner reverse-depends on retired historical owner")


def _check_cli() -> None:
    source = CLI.read_text()
    required = (
        "from qpx_harness.issue45_first_linear import main as "
        "first_linear_main, self_test as first_linear_self_test"
    )
    if required not in source:
        raise AssertionError("stable inventory-first-linear CLI is not semantic-owned")
    if "from qpx_harness.petsc_first_linear_diagnostic import" in source:
        raise AssertionError("stable CLI imports historical first-linear owner")
    if '"inventory-first-linear":' not in source:
        raise AssertionError("stable inventory-first-linear command missing")


def _negative_control() -> None:
    source = "from qpx_harness import petsc_first_linear_diagnostic as old\n"
    path = ROOT / "tests" / "synthetic_retirement_consumer.py"
    if not _imports_source_control(source, path):
        raise AssertionError("retirement consumer-detection negative control failed")


def _imports_source_control(source: str, path: Path) -> bool:
    tree = ast.parse(source, filename=str(path))
    module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
    package = module.rpartition(".")[0]
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        base = node.module or ""
        if node.level:
            try:
                base = importlib.util.resolve_name(
                    "." * node.level + base, package
                )
            except (ImportError, ValueError):
                continue
        if base == "qpx_harness" and any(
            alias.name == "petsc_first_linear_diagnostic" for alias in node.names
        ):
            return True
    return False


def main() -> int:
    try:
        state = _check_zero_consumer_or_retired()
        print(
            "ISSUE48_WP22_FIRST_LINEAR_RETIREMENT_CHECK: "
            f"legacy-state={state} consumers=NONE"
        )
        _check_canonical_owners()
        print("ISSUE48_WP22_FIRST_LINEAR_RETIREMENT_CHECK: canonical-owners=PASS")
        _check_cli()
        print("ISSUE48_WP22_FIRST_LINEAR_RETIREMENT_CHECK: stable-cli=PASS")
        _negative_control()
        print("ISSUE48_WP22_FIRST_LINEAR_RETIREMENT_CHECK: negative-control=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP22_FIRST_LINEAR_RETIREMENT_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print(
        "ISSUE48_WP22_FIRST_LINEAR_RETIREMENT_CHARACTERIZATION: "
        f"PASS state={state}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
