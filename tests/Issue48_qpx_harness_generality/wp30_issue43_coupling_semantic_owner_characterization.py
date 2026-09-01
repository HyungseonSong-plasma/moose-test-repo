#!/usr/bin/env python3
"""P0 characterization for the post-retirement Issue43 coupling semantic owner."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import issue43_coupling_diagnostic as semantic
from qpx_harness.moose import log as moose_log
from qpx_harness.petsc import jacobian as petsc_jacobian
from qpx_harness.petsc import log as petsc_log
from recipes import issue43_coupling_diagnostic as recipe

SEMANTIC_PATH = ROOT / "qpx_harness" / "issue43_coupling_diagnostic.py"
LEGACY_PATH = ROOT / "qpx_harness" / "fast_plasma_coupling_diagnostic.py"
CLI_PATH = ROOT / "scripts" / "qpx.py"
LEGACY_IMPORT_TOKEN = "fast_plasma_coupling_diagnostic"


def _load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("issue48_wp30_qpx_cli", CLI_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load scripts/qpx.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_no_legacy_dependency(source: str) -> None:
    if LEGACY_IMPORT_TOKEN in source:
        raise AssertionError("semantic owner still references retired coupling shell")


def _check_owner_topology() -> None:
    if not SEMANTIC_PATH.is_file():
        raise AssertionError("Issue43 coupling semantic owner is missing")
    if LEGACY_PATH.exists():
        raise AssertionError("retired historical coupling shell still exists")
    source = SEMANTIC_PATH.read_text()
    for required in (
        "from recipes import issue43_coupling_diagnostic as recipe",
        "from .moose import log as moose_log",
        "from .petsc import jacobian as petsc_jacobian",
        "from .petsc import log as petsc_log",
        "def run_preflight(",
        "def run_runtime(",
        "def run_jacobian_runtime(",
        "def main(",
        "def self_test(",
    ):
        if required not in source:
            raise AssertionError(f"semantic owner boundary missing: {required}")
    _assert_no_legacy_dependency(source)


def _check_recipe_and_primitive_backing() -> None:
    status = semantic.recipe_backing_status()
    if not status or not all(status.values()):
        raise AssertionError(f"semantic backing drift: {status}")
    fixture = """[Executioner]\n  type = Transient\n[]\n[Outputs]\n  [console]\n    type = Console\n  []\n[]\n"""
    for jacobian_test in (False, True):
        observed = semantic.instrument_input(fixture, jacobian_test=jacobian_test)
        expected = recipe.instrument_input(fixture, jacobian_test=jacobian_test)
        if observed != expected:
            raise AssertionError(f"recipe construction drift jacobian_test={jacobian_test}")
    if semantic._parse_variable_residuals is not moose_log.parse_variable_residual_norms:
        raise AssertionError("variable-residual parser is not generic-backed")
    if semantic._parse_scaling_factors is not moose_log.parse_automatic_scaling_factors:
        raise AssertionError("scaling parser is not generic-backed")
    if semantic._parse_pc_failure_reason is not petsc_log.parse_pc_failure_reason:
        raise AssertionError("PC failure parser is not generic-backed")
    if semantic._parse_jacobian_tests is not petsc_jacobian.parse_comparisons:
        raise AssertionError("Jacobian parser is not generic-backed")


def _check_stable_cli_route() -> None:
    cli = _load_cli()
    if cli.fast_coupling_diagnostic_main is not semantic.main:
        raise AssertionError("stable coupling CLI main is not semantic-owner backed")
    if cli.fast_coupling_diagnostic_self_test is not semantic.self_test:
        raise AssertionError("stable coupling CLI self-test is not semantic-owner backed")
    source = CLI_PATH.read_text()
    required = (
        "from qpx_harness.issue43_coupling_diagnostic import main as fast_coupling_diagnostic_main, self_test as fast_coupling_diagnostic_self_test",
        'if command == "fast-coupling-diagnostic":',
        "return fast_coupling_diagnostic_main(rest)",
    )
    for token in required:
        if token not in source:
            raise AssertionError(f"stable coupling CLI surface missing: {token}")
    legacy_import = (
        "from qpx_harness.fast_plasma_coupling_diagnostic import main as "
        "fast_coupling_diagnostic_main"
    )
    if legacy_import in source:
        raise AssertionError("stable CLI still imports the retired coupling shell")


def _check_self_test_route() -> None:
    if semantic.self_test() != 0:
        raise AssertionError("Issue43 coupling semantic owner self-test failed")


def _negative_control() -> None:
    source = SEMANTIC_PATH.read_text()
    marker = "from recipes import issue43_coupling_diagnostic as recipe"
    if marker not in source:
        raise AssertionError("semantic recipe import baseline missing")
    mutated = source.replace(
        marker,
        marker + "\nfrom . import fast_plasma_coupling_diagnostic as runtime_shell",
        1,
    )
    try:
        _assert_no_legacy_dependency(mutated)
    except AssertionError:
        return
    raise AssertionError("legacy dependency negative control was accepted")


def main() -> int:
    try:
        _check_owner_topology()
        print("ISSUE48_WP30_ISSUE43_COUPLING_CHECK: owner-topology=PASS")
        print("ISSUE48_WP30_ISSUE43_COUPLING_CHECK: legacy-retired=PASS")
        _check_recipe_and_primitive_backing()
        print("ISSUE48_WP30_ISSUE43_COUPLING_CHECK: recipe-and-primitives=PASS")
        _check_stable_cli_route()
        print("ISSUE48_WP30_ISSUE43_COUPLING_CHECK: stable-cli-route=PASS")
        _check_self_test_route()
        print("ISSUE48_WP30_ISSUE43_COUPLING_CHECK: self-test-route=PASS")
        _negative_control()
        print("ISSUE48_WP30_ISSUE43_COUPLING_CHECK: negative-control=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP30_ISSUE43_COUPLING_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP30_ISSUE43_COUPLING_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
