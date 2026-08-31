#!/usr/bin/env python3
"""P0 characterization for the Issue46 FD-reference semantic runtime owner."""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import issue46_fd_reference as semantic

LEGACY_MODULE = "qpx_harness.jacobian_fd_reference_audit"
SEMANTIC_MODULE = "qpx_harness.issue46_fd_reference"
COMPAT_MODULE = "qpx_harness.compat.issue46_fd_reference"
LEGACY_PATH = ROOT / "qpx_harness" / "jacobian_fd_reference_audit.py"
SEMANTIC_PATH = ROOT / "qpx_harness" / "issue46_fd_reference.py"
COMPAT_PATH = ROOT / "qpx_harness" / "compat" / "issue46_fd_reference.py"
CLI_PATH = ROOT / "scripts" / "qpx.py"

EXPECTED_RECIPE_BINDINGS = {
    "predict_fd_step_quantization",
    "historical_evr1_prediction",
    "historical_mechanism_evidence",
    "termination_admissibility",
    "runtime_mechanism_applicability",
    "evidence_provenance_status",
    "directional_localization",
    "instrument_ds_reference",
    "remove_fd_type_pair",
    "mask_petsc_pair_lines",
    "analyze_ds_runtime",
}


def _resolved_imports_source(source: str, *, path: Path) -> set[str]:
    tree = ast.parse(source, filename=str(path))
    module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
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


def _resolved_imports(path: Path) -> set[str]:
    return _resolved_imports_source(path.read_text(), path=path)


def _production_consumers(module_name: str, owner: Path) -> set[str]:
    consumers: set[str] = set()
    for rel_root in ("qpx_harness", "recipes", "scripts", "performance"):
        base = ROOT / rel_root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if path == owner or "__pycache__" in path.parts:
                continue
            try:
                imports = _resolved_imports(path)
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            if module_name in imports:
                consumers.add(str(path.relative_to(ROOT)))
    return consumers


def _load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("issue48_wp27_qpx_cli", CLI_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load scripts/qpx.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_owner_topology() -> None:
    if not LEGACY_PATH.is_file():
        raise AssertionError("FD runtime shell unexpectedly absent before convergence")
    if not SEMANTIC_PATH.is_file():
        raise AssertionError("Issue46 FD semantic owner is missing")
    if not COMPAT_PATH.is_file():
        raise AssertionError("Issue46 FD compat import is missing")

    legacy_consumers = _production_consumers(LEGACY_MODULE, LEGACY_PATH)
    if legacy_consumers != {"qpx_harness/issue46_fd_reference.py"}:
        raise AssertionError(
            "legacy FD shell production topology drift: "
            f"{sorted(legacy_consumers)}"
        )

    semantic_consumers = _production_consumers(SEMANTIC_MODULE, SEMANTIC_PATH)
    expected_semantic = {
        "qpx_harness/compat/issue46_fd_reference.py",
        "scripts/qpx.py",
    }
    if semantic_consumers != expected_semantic:
        raise AssertionError(
            "semantic FD owner production topology drift: "
            f"expected={sorted(expected_semantic)} observed={sorted(semantic_consumers)}"
        )

    compat_consumers = _production_consumers(COMPAT_MODULE, COMPAT_PATH)
    if compat_consumers:
        raise AssertionError(
            "FD compat still has production consumers: "
            f"{sorted(compat_consumers)}"
        )


def _check_dependency_boundary() -> None:
    semantic_imports = _resolved_imports(SEMANTIC_PATH)
    if "recipes.issue46_fd_reference" not in semantic_imports:
        raise AssertionError("semantic owner does not import the Issue46 FD recipe")
    if LEGACY_MODULE not in semantic_imports:
        raise AssertionError("semantic owner lost the bounded legacy runtime-shell dependency")

    compat_imports = _resolved_imports(COMPAT_PATH)
    if SEMANTIC_MODULE not in compat_imports:
        raise AssertionError("compat does not re-export the semantic FD owner")
    if LEGACY_MODULE in compat_imports:
        raise AssertionError("compat still imports the legacy FD runtime shell")
    if "recipes.issue46_fd_reference" in compat_imports:
        raise AssertionError("compat still owns recipe composition")


def _check_compat_surface() -> None:
    source = COMPAT_PATH.read_text()
    required = (
        "from qpx_harness.issue46_fd_reference import main, recipe_backing_status, self_test",
        '__all__ = ["main", "recipe_backing_status", "self_test"]',
    )
    for token in required:
        if token not in source:
            raise AssertionError(f"compat semantic re-export surface drift: {token}")
    tree = ast.parse(source, filename=str(COMPAT_PATH))
    public_defs = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    if public_defs:
        raise AssertionError(f"compat unexpectedly owns executable definitions: {public_defs}")


def _check_recipe_backing() -> None:
    status = semantic.recipe_backing_status()
    if set(status) != EXPECTED_RECIPE_BINDINGS:
        raise AssertionError(f"recipe backing surface drift: {sorted(status)}")
    failed = sorted(name for name, ok in status.items() if not ok)
    if failed:
        raise AssertionError(f"recipe backing identity failed: {failed}")


def _check_stable_cli_route() -> None:
    cli = _load_cli()
    if cli.fd_reference_main is not semantic.main:
        raise AssertionError("stable CLI main does not resolve to semantic FD owner")
    if cli.fd_reference_self_test is not semantic.self_test:
        raise AssertionError("stable CLI self-test does not resolve to semantic FD owner")

    source = CLI_PATH.read_text()
    required = (
        "from qpx_harness.issue46_fd_reference import main as fd_reference_main, self_test as fd_reference_self_test",
        'if command == "inventory-fd-reference":',
        "return fd_reference_main(rest)",
    )
    for token in required:
        if token not in source:
            raise AssertionError(f"stable FD CLI surface missing: {token}")
    if "from qpx_harness.compat.issue46_fd_reference import" in source:
        raise AssertionError("stable CLI still imports the FD compat adapter")


def _check_self_test_route() -> None:
    if semantic.self_test() != 0:
        raise AssertionError("semantic FD owner self-test failed")


def _negative_control() -> None:
    source = CLI_PATH.read_text()
    semantic_import = (
        "from qpx_harness.issue46_fd_reference import main as fd_reference_main, "
        "self_test as fd_reference_self_test"
    )
    compat_import = (
        "from qpx_harness.compat.issue46_fd_reference import main as fd_reference_main, "
        "self_test as fd_reference_self_test"
    )
    if semantic_import not in source:
        raise AssertionError("CLI semantic import baseline missing")
    mutated = source.replace(semantic_import, compat_import, 1)
    imports = _resolved_imports_source(mutated, path=CLI_PATH)
    if COMPAT_MODULE not in imports:
        raise AssertionError("compat CLI negative control was not detected")
    if SEMANTIC_MODULE in imports:
        raise AssertionError("semantic owner remained after compat CLI mutation")


def main() -> int:
    try:
        _check_owner_topology()
        print("ISSUE48_WP27_ISSUE46_FD_SEMANTIC_CHECK: owner-topology=PASS")
        _check_dependency_boundary()
        print("ISSUE48_WP27_ISSUE46_FD_SEMANTIC_CHECK: dependency-boundary=PASS")
        _check_compat_surface()
        print("ISSUE48_WP27_ISSUE46_FD_SEMANTIC_CHECK: compat-surface=PASS")
        _check_recipe_backing()
        print("ISSUE48_WP27_ISSUE46_FD_SEMANTIC_CHECK: recipe-backing=PASS")
        _check_stable_cli_route()
        print("ISSUE48_WP27_ISSUE46_FD_SEMANTIC_CHECK: stable-cli-route=PASS")
        _check_self_test_route()
        print("ISSUE48_WP27_ISSUE46_FD_SEMANTIC_CHECK: self-test-route=PASS")
        _negative_control()
        print("ISSUE48_WP27_ISSUE46_FD_SEMANTIC_CHECK: negative-control=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP27_ISSUE46_FD_SEMANTIC_CHARACTERIZATION: FAIL ({exc})")
        return 1

    print("ISSUE48_WP27_ISSUE46_FD_SEMANTIC_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
