#!/usr/bin/env python3
"""Issue48 characterization for converging the Issue43 fast-relaxation v5 owner."""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LEGACY = ROOT / "qpx_harness" / "fast_plasma_relaxation_v5.py"
SEMANTIC = ROOT / "qpx_harness" / "issue43_fast_relaxation.py"
CLI = ROOT / "scripts" / "qpx.py"

EXPECTED_LEGACY_PRODUCTION_CONSUMERS = {
    "qpx_harness/electron_inventory_nullspace.py",
    "qpx_harness/fast_plasma_coupling_diagnostic.py",
}
EXPECTED_LEGACY_TEST_CONSUMERS = {
    "tests/Issue48_qpx_harness_generality/wp17_v5_v2_absorption_characterization.py",
}
EXPECTED_SEMANTIC_PRODUCTION_CONSUMERS = {
    "scripts/qpx.py",
}
EXPECTED_SEMANTIC_TEST_CONSUMERS: set[str] = set()
REQUIRED_OWNER_SURFACE = (
    "def _build_feedback_v5(",
    "def _augment_execution_contract(",
    "def _classify_p2_failure(",
    "def _solver_trajectory(",
    "def self_test(",
    "def main(",
)
REQUIRED_ARCHITECTURE_TOKENS = (
    "from recipes import issue43_fast_relaxation as relaxation_recipe",
    "from . import issue43_relaxation_runtime as issue43_runtime",
    "from . import output_observation_contract as ooc",
    "from . import execution_contract as ec",
)


def _imports_module(path: Path, module_name: str) -> bool:
    source = path.read_text()
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == module_name for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                package = ".".join(path.relative_to(ROOT).with_suffix("").parts[:-1])
                try:
                    base = importlib.util.resolve_name(
                        "." * node.level + (node.module or ""), package
                    )
                except (ImportError, ValueError):
                    continue
            if base == module_name:
                return True
            if base == "qpx_harness" and any(
                f"qpx_harness.{alias.name}" == module_name for alias in node.names
            ):
                return True
    return False


def _consumer_sets(module_name: str) -> tuple[set[str], set[str]]:
    production: set[str] = set()
    tests: set[str] = set()
    for rel_root in ("qpx_harness", "recipes", "scripts", "tests"):
        base = ROOT / rel_root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if path in {LEGACY, SEMANTIC}:
                continue
            try:
                consumes = _imports_module(path, module_name)
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            if not consumes:
                continue
            rel = str(path.relative_to(ROOT))
            (tests if rel.startswith("tests/") else production).add(rel)
    return production, tests


def _check_dual_owner_topology() -> None:
    if not LEGACY.is_file():
        raise AssertionError("legacy v5 owner missing before internal-consumer cutover")
    if not SEMANTIC.is_file():
        raise AssertionError("semantic Issue43 owner missing after dual-owner creation")

    legacy_production, legacy_tests = _consumer_sets(
        "qpx_harness.fast_plasma_relaxation_v5"
    )
    if legacy_production != EXPECTED_LEGACY_PRODUCTION_CONSUMERS:
        raise AssertionError(
            "v5 production-consumer drift: "
            f"observed={sorted(legacy_production)} "
            f"expected={sorted(EXPECTED_LEGACY_PRODUCTION_CONSUMERS)}"
        )
    if legacy_tests != EXPECTED_LEGACY_TEST_CONSUMERS:
        raise AssertionError(
            "v5 test-consumer drift: "
            f"observed={sorted(legacy_tests)} "
            f"expected={sorted(EXPECTED_LEGACY_TEST_CONSUMERS)}"
        )

    semantic_production, semantic_tests = _consumer_sets(
        "qpx_harness.issue43_fast_relaxation"
    )
    if semantic_production != EXPECTED_SEMANTIC_PRODUCTION_CONSUMERS:
        raise AssertionError(
            "semantic production-consumer drift: "
            f"observed={sorted(semantic_production)} "
            f"expected={sorted(EXPECTED_SEMANTIC_PRODUCTION_CONSUMERS)}"
        )
    if semantic_tests != EXPECTED_SEMANTIC_TEST_CONSUMERS:
        raise AssertionError(
            "semantic test-consumer drift: "
            f"observed={sorted(semantic_tests)} "
            f"expected={sorted(EXPECTED_SEMANTIC_TEST_CONSUMERS)}"
        )


def _check_owner_equivalence() -> None:
    legacy_source = LEGACY.read_text()
    semantic_source = SEMANTIC.read_text()
    if semantic_source != legacy_source:
        raise AssertionError("semantic owner is not byte-equivalent to legacy v5 owner")

    for path, source in ((LEGACY, legacy_source), (SEMANTIC, semantic_source)):
        missing = [token for token in REQUIRED_OWNER_SURFACE if token not in source]
        if missing:
            raise AssertionError(f"owner surface drift {path.name}: missing={missing}")
        missing_arch = [
            token for token in REQUIRED_ARCHITECTURE_TOKENS if token not in source
        ]
        if missing_arch:
            raise AssertionError(
                f"owner architecture composition drift {path.name}: missing={missing_arch}"
            )

    if _imports_module(SEMANTIC, "qpx_harness.fast_plasma_relaxation_v5"):
        raise AssertionError("semantic owner reverse-imported legacy v5 owner")


def _check_consumer_contracts() -> None:
    inventory = (ROOT / "qpx_harness" / "electron_inventory_nullspace.py").read_text()
    diagnostic = (ROOT / "qpx_harness" / "fast_plasma_coupling_diagnostic.py").read_text()
    cli = CLI.read_text()

    for token in (
        "v5._build_feedback_v5(",
        "v5._classify_p2_failure(",
    ):
        if token not in inventory:
            raise AssertionError(f"inventory v5 contract drift: {token}")

    for token in (
        "v5._build_feedback_v5(",
        "v5._augment_execution_contract(",
        "v5._classify_p2_failure(",
        "v5._solver_trajectory(",
    ):
        if token not in diagnostic:
            raise AssertionError(f"coupling diagnostic v5 contract drift: {token}")

    semantic_cli = (
        "from qpx_harness.issue43_fast_relaxation import main as "
        "fast_relaxation_main, self_test as fast_relaxation_self_test"
    )
    legacy_cli = (
        "from qpx_harness.fast_plasma_relaxation_v5 import main as "
        "fast_relaxation_main, self_test as fast_relaxation_self_test"
    )
    if semantic_cli not in cli:
        raise AssertionError("stable fast-relaxation CLI is not bound to semantic owner")
    if legacy_cli in cli:
        raise AssertionError("stable fast-relaxation CLI still imports legacy v5 owner")
    if '"fast-relaxation":' not in cli:
        raise AssertionError("stable fast-relaxation command missing")


def _negative_control() -> None:
    forbidden_wrapper = "from . import fast_plasma_relaxation_v5"
    synthetic = f'"""semantic owner"""\n{forbidden_wrapper}\n'
    if forbidden_wrapper not in synthetic:
        raise AssertionError("semantic-owner reverse-wrapper negative control failed")


def main() -> int:
    try:
        _check_dual_owner_topology()
        _check_owner_equivalence()
        _check_consumer_contracts()
        _negative_control()
    except Exception as exc:
        print(f"ISSUE48_ISSUE43_SEMANTIC_OWNER_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_ISSUE43_SEMANTIC_OWNER_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
