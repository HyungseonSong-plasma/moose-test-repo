#!/usr/bin/env python3
"""P0 characterization for the stable Issue46 FD-reference CLI cutover."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness.compat import issue46_fd_reference as compat


def _check_recipe_backing() -> None:
    status = compat.recipe_backing_status()
    failed = [name for name, ok in status.items() if not ok]
    if failed:
        raise AssertionError(f"compatibility bindings are not recipe-backed: {failed}")


def _check_stable_cli_route() -> None:
    script = ROOT / "scripts" / "qpx.py"
    source = script.read_text()
    expected_import = (
        "from qpx_harness.compat.issue46_fd_reference import main as fd_reference_main, "
        "self_test as fd_reference_self_test"
    )
    if expected_import not in source:
        raise AssertionError("stable CLI does not import the Issue46 compatibility adapter")
    if "from qpx_harness.jacobian_fd_reference_audit import main as fd_reference_main" in source:
        raise AssertionError("stable CLI still directly imports the mixed Issue46 owner")

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


def _check_compatibility_boundary() -> None:
    source = (ROOT / "qpx_harness" / "compat" / "issue46_fd_reference.py").read_text()
    if "from recipes import issue46_fd_reference as recipe" not in source:
        raise AssertionError("compatibility adapter does not import the thin recipe")
    recipe_source = (ROOT / "recipes" / "issue46_fd_reference.py").read_text()
    for forbidden in (
        "jacobian_fd_reference_audit",
        "augmented_jacobian_localization",
        "electron_inventory_nullspace",
        "petsc_first_linear_diagnostic",
        "fast_plasma_coupling_diagnostic",
    ):
        if forbidden in recipe_source:
            raise AssertionError(f"reverse dependency leaked into recipe: {forbidden}")


def main() -> int:
    try:
        _check_recipe_backing()
        print("ISSUE48_WP4_ISSUE46_CLI_CHECK: recipe-backing=PASS")
        _check_stable_cli_route()
        print("ISSUE48_WP4_ISSUE46_CLI_CHECK: stable-route=PASS")
        _check_compatibility_boundary()
        print("ISSUE48_WP4_ISSUE46_CLI_CHECK: compatibility-boundary=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP4_ISSUE46_CLI_CUTOVER: FAIL ({exc})")
        return 1
    print("ISSUE48_WP4_ISSUE46_CLI_CUTOVER: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
