#!/usr/bin/env python3
"""P0 characterization for the Issue46 localization CLI semantic-owner cutover."""
from __future__ import annotations

import ast
import importlib
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LEGACY_MODULE = "qpx_harness.augmented_jacobian_localization"
SEMANTIC_MODULE = "qpx_harness.issue46_jacobian_localization"
LEGACY_PATH = ROOT / "qpx_harness" / "augmented_jacobian_localization.py"
SEMANTIC_PATH = ROOT / "qpx_harness" / "issue46_jacobian_localization.py"
FD_AUDIT_PATH = ROOT / "qpx_harness" / "jacobian_fd_reference_audit.py"
CLI_PATH = ROOT / "scripts" / "qpx.py"

EXPECTED_LEGACY_PRODUCTION_CONSUMERS: set[str] = set()
EXPECTED_SEMANTIC_PRODUCTION_CONSUMERS = {
    "qpx_harness/jacobian_fd_reference_audit.py",
    "scripts/qpx.py",
}


def _imports_module_source(
    source: str, *, path: Path, module_name: str
) -> bool:
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


def _imports_module(path: Path, module_name: str) -> bool:
    return _imports_module_source(path.read_text(), path=path, module_name=module_name)


def _production_consumers(module_name: str, owner: Path) -> set[str]:
    consumers: set[str] = set()
    for rel_root in ("qpx_harness", "recipes", "scripts", "performance"):
        base = ROOT / rel_root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if path == owner:
                continue
            try:
                consumes = _imports_module(path, module_name)
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            if consumes:
                consumers.add(str(path.relative_to(ROOT)))
    return consumers


def _load_cli_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("issue48_wp25_qpx_cli", CLI_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load scripts/qpx.py for binding characterization")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_production_topology() -> None:
    if not LEGACY_PATH.is_file():
        raise AssertionError("legacy owner unexpectedly absent before retirement phase")
    if not SEMANTIC_PATH.is_file():
        raise AssertionError("semantic Issue46 owner is missing")

    legacy_consumers = _production_consumers(LEGACY_MODULE, LEGACY_PATH)
    semantic_consumers = _production_consumers(SEMANTIC_MODULE, SEMANTIC_PATH)
    if legacy_consumers != EXPECTED_LEGACY_PRODUCTION_CONSUMERS:
        raise AssertionError(
            "legacy production consumer drift: "
            f"expected={EXPECTED_LEGACY_PRODUCTION_CONSUMERS!r} "
            f"observed={legacy_consumers!r}"
        )
    if semantic_consumers != EXPECTED_SEMANTIC_PRODUCTION_CONSUMERS:
        raise AssertionError(
            "semantic production consumer drift: "
            f"expected={EXPECTED_SEMANTIC_PRODUCTION_CONSUMERS!r} "
            f"observed={semantic_consumers!r}"
        )


def _check_cli_binding() -> None:
    semantic = importlib.import_module(SEMANTIC_MODULE)
    cli = _load_cli_module()
    if cli.jac_localization_main is not semantic.main:
        raise AssertionError("CLI main binding does not point to semantic Issue46 owner")
    if cli.jac_localization_self_test is not semantic.self_test:
        raise AssertionError("CLI self-test binding does not point to semantic Issue46 owner")


def _check_stable_entrypoint() -> None:
    source = CLI_PATH.read_text()
    required = (
        "from qpx_harness.issue46_jacobian_localization import main as jac_localization_main, self_test as jac_localization_self_test",
        '"inventory-jacobian-localization": "prepare the Issue46 augmented Jacobian block-localization audit"',
        'if command == "inventory-jacobian-localization":',
        "return jac_localization_main(rest)",
    )
    for token in required:
        if token not in source:
            raise AssertionError(f"stable CLI surface missing: {token}")
    if "from qpx_harness.augmented_jacobian_localization import" in source:
        raise AssertionError("CLI still imports legacy augmented owner")


def _check_self_test_route() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            "inventory-jacobian-localization",
            "--self-test",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"stable CLI semantic self-test failed rc={proc.returncode}: {proc.stdout}"
        )
    for marker in (
        "ISSUE46_JAC_LOCALIZATION_SELFTEST: PASS",
        "ISSUE46_JAC_LOCALIZATION_RUNTIME_SELFTEST: PASS",
    ):
        if marker not in proc.stdout:
            raise AssertionError(f"stable CLI lost semantic marker: {marker}")


def _negative_control() -> None:
    source = CLI_PATH.read_text()
    semantic_import = (
        "from qpx_harness.issue46_jacobian_localization import main as "
        "jac_localization_main, self_test as jac_localization_self_test"
    )
    legacy_import = (
        "from qpx_harness.augmented_jacobian_localization import main as "
        "jac_localization_main, self_test as jac_localization_self_test"
    )
    if semantic_import not in source:
        raise AssertionError("semantic import baseline missing for negative control")
    mutated = source.replace(semantic_import, legacy_import, 1)
    if not _imports_module_source(mutated, path=CLI_PATH, module_name=LEGACY_MODULE):
        raise AssertionError("legacy CLI mutation was not detected")
    if _imports_module_source(mutated, path=CLI_PATH, module_name=SEMANTIC_MODULE):
        raise AssertionError("semantic owner remained after legacy CLI mutation")


def main() -> int:
    try:
        _check_production_topology()
        print("ISSUE48_WP25_ISSUE46_CLI_CHECK: production-topology=PASS")
        _check_cli_binding()
        print("ISSUE48_WP25_ISSUE46_CLI_CHECK: cli-binding=PASS")
        _check_stable_entrypoint()
        print("ISSUE48_WP25_ISSUE46_CLI_CHECK: stable-entrypoint=PASS")
        _check_self_test_route()
        print("ISSUE48_WP25_ISSUE46_CLI_CHECK: self-test-route=PASS")
        _negative_control()
        print("ISSUE48_WP25_ISSUE46_CLI_CHECK: negative-control=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP25_ISSUE46_CLI_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP25_ISSUE46_CLI_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
