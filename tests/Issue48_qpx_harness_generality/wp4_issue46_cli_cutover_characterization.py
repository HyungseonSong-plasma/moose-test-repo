#!/usr/bin/env python3
"""P0 characterization for the stable Issue46 FD-reference CLI cutover."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import issue46_fd_reference as semantic


def _check_recipe_backing() -> None:
    status = semantic.recipe_backing_status()
    failed = [name for name, ok in status.items() if not ok]
    if failed:
        raise AssertionError(f"semantic bindings are not recipe-backed: {failed}")


def _check_stable_cli_route() -> None:
    script = ROOT / "scripts" / "qpx.py"
    source = script.read_text()
    expected_import = (
        "from qpx_harness.issue46_fd_reference import main as fd_reference_main, "
        "self_test as fd_reference_self_test"
    )
    if expected_import not in source:
        raise AssertionError("stable CLI does not import the Issue46 FD semantic owner")
    if "from qpx_harness.compat.issue46_fd_reference import" in source:
        raise AssertionError("stable CLI still imports the retired compatibility adapter")
    if "from qpx_harness.jacobian_fd_reference_audit import" in source:
        raise AssertionError("stable CLI imports the historical FD proxy")

    run = subprocess.run(
        [sys.executable, str(script), "inventory-fd-reference", "--self-test"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if run.returncode != 0:
        raise AssertionError(
            f"stable inventory-fd-reference --self-test failed rc={run.returncode}:\n{run.stdout}"
        )
    if "ISSUE46_FD_REFERENCE_SELFTEST: PASS" not in run.stdout:
        raise AssertionError(
            "stable inventory-fd-reference self-test marker missing:\n" + run.stdout
        )


def _check_semantic_boundary() -> None:
    semantic_source = (ROOT / "qpx_harness" / "issue46_fd_reference.py").read_text()
    if "from recipes import issue46_fd_reference as recipe" not in semantic_source:
        raise AssertionError("semantic owner does not import the thin Issue46 FD recipe")
    if "jacobian_fd_reference_audit as runtime_shell" in semantic_source:
        raise AssertionError("semantic owner still delegates runtime to the historical FD shell")
    if "qpx_harness.compat.issue46_fd_reference" in semantic_source:
        raise AssertionError("semantic owner reverse-depends on the retired compatibility adapter")
    for required in (
        "def run_preflight(",
        "def run_runtime(",
        "def main(",
        "def self_test(",
    ):
        if required not in semantic_source:
            raise AssertionError(f"semantic owner does not own runtime surface: {required}")

    legacy_source = (ROOT / "qpx_harness" / "jacobian_fd_reference_audit.py").read_text()
    if "from . import issue46_fd_reference as _owner" not in legacy_source:
        raise AssertionError("historical FD module is not a semantic-owner proxy")
    for forbidden in ("def run_preflight(", "def run_runtime(", "from recipes import"):
        if forbidden in legacy_source:
            raise AssertionError(f"historical FD proxy still owns runtime/policy: {forbidden}")

    recipe_source = (ROOT / "recipes" / "issue46_fd_reference.py").read_text()
    for forbidden in (
        "jacobian_fd_reference_audit",
        "augmented_jacobian_localization",
        "electron_inventory_nullspace",
        "petsc_first_linear_diagnostic",
        "fast_plasma_coupling_diagnostic",
        "qpx_harness.compat.issue46_fd_reference",
    ):
        if forbidden in recipe_source:
            raise AssertionError(f"reverse dependency leaked into recipe: {forbidden}")


def _negative_control() -> None:
    script = ROOT / "scripts" / "qpx.py"
    source = script.read_text()
    semantic_import = (
        "from qpx_harness.issue46_fd_reference import main as fd_reference_main, "
        "self_test as fd_reference_self_test"
    )
    legacy_import = (
        "from qpx_harness.jacobian_fd_reference_audit import main as fd_reference_main, "
        "self_test as fd_reference_self_test"
    )
    if semantic_import not in source:
        raise AssertionError("stable semantic CLI import baseline missing")
    mutated = source.replace(semantic_import, legacy_import, 1)
    if legacy_import not in mutated or semantic_import in mutated:
        raise AssertionError("legacy-route negative control did not create the stale topology")


def main() -> int:
    try:
        _check_recipe_backing()
        print("ISSUE48_WP4_ISSUE46_CLI_CHECK: recipe-backing=PASS")
        _check_stable_cli_route()
        print("ISSUE48_WP4_ISSUE46_CLI_CHECK: stable-route=PASS")
        _check_semantic_boundary()
        print("ISSUE48_WP4_ISSUE46_CLI_CHECK: semantic-boundary=PASS")
        _negative_control()
        print("ISSUE48_WP4_ISSUE46_CLI_CHECK: negative-control=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP4_ISSUE46_CLI_CUTOVER: FAIL ({exc})")
        return 1
    print("ISSUE48_WP4_ISSUE46_CLI_CUTOVER: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
