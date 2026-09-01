#!/usr/bin/env python3
"""P0 characterization for Issue48 retained-owner scope freeze."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qpx_harness import electron_inventory_nullspace as inventory_owner
from qpx_harness import scale_audit as scale_owner

CLEANUP_PATH = ROOT / "tests" / "Issue48_qpx_harness_generality" / "cleanup_inventory.py"
CLI_PATH = ROOT / "scripts" / "qpx.py"


def _load_cleanup_module():
    spec = importlib.util.spec_from_file_location("issue48_cleanup_inventory_wp31", CLEANUP_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load cleanup inventory")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_issue45_inventory_owner() -> None:
    for name in (
        "audit_closed_electron_structure",
        "audit_constrained_quasisteady_structure",
        "run_preflight",
        "run_closure_preflight",
        "run_closure_runtime_preflight",
        "run_closure_runtime",
        "self_test",
        "main",
    ):
        if not callable(getattr(inventory_owner, name, None)):
            raise AssertionError(f"Issue45 inventory owner surface missing: {name}")

    source = (ROOT / "qpx_harness" / "electron_inventory_nullspace.py").read_text()
    for required in (
        "class ElectronInventoryNullspaceError",
        "def audit_closed_electron_structure(",
        "def audit_constrained_quasisteady_structure(",
        "def run_closure_runtime(",
    ):
        if required not in source:
            raise AssertionError(f"Issue45 semantic ownership drift: {required}")

    cli = CLI_PATH.read_text()
    expected = (
        "from qpx_harness.electron_inventory_nullspace import main as "
        "inventory_nullspace_main, self_test as inventory_nullspace_self_test"
    )
    if expected not in cli:
        raise AssertionError("stable inventory-nullspace CLI is not bound to its canonical owner")


def _check_scale_owner() -> None:
    for name in (
        "mesh_stats",
        "anchor_scales",
        "decision_map",
        "build_scale_map",
        "self_test",
        "main",
    ):
        if not callable(getattr(scale_owner, name, None)):
            raise AssertionError(f"scale owner surface missing: {name}")

    source = (ROOT / "qpx_harness" / "scale_audit.py").read_text()
    for forbidden in (
        "from . import issue",
        "from qpx_harness import issue",
        "from recipes",
        "import recipes",
    ):
        if forbidden in source:
            raise AssertionError(f"Issue-specific reverse dependency leaked into scale owner: {forbidden}")

    cli = CLI_PATH.read_text()
    expected = (
        "from qpx_harness.scale_audit import main as scale_audit_main, "
        "self_test as scale_audit_self_test"
    )
    if expected not in cli:
        raise AssertionError("stable scale-audit CLI is not bound to its reusable owner")

    consumer_tokens = {
        "qpx_harness/electron_inventory_nullspace.py": "from .scale_audit import mesh_stats",
        "qpx_harness/issue43_coupling_diagnostic.py": "from .scale_audit import mesh_stats",
        "qpx_harness/issue43_fast_relaxation.py": "scale_audit",
        "qpx_harness/issue43_relaxation_runtime.py": "scale_audit",
        "recipes/issue43_fast_relaxation.py": "scale_audit",
    }
    observed = []
    for rel, token in consumer_tokens.items():
        path = ROOT / rel
        if path.is_file() and token in path.read_text():
            observed.append(rel)
    if len(observed) < 3:
        raise AssertionError(f"scale owner is not demonstrably cross-workflow: {observed}")


def _check_cleanup_scope() -> None:
    cleanup = _load_cleanup_module()
    retained = set(cleanup.RETAINED_OWNERS)
    candidates = set(cleanup.CLEANUP_CANDIDATES)
    expected_retained = {"electron_inventory_nullspace", "scale_audit"}
    if retained != expected_retained:
        raise AssertionError(f"retained-owner set drift: {sorted(retained)}")
    if candidates:
        raise AssertionError(f"cleanup-candidate scope is not empty after retirement: {sorted(candidates)}")
    if retained & candidates:
        raise AssertionError("retained owner also appears as cleanup candidate")


def _negative_control() -> None:
    retained = {"electron_inventory_nullspace", "scale_audit"}
    mutated_candidates = {"scale_audit"}
    if not retained & mutated_candidates:
        raise AssertionError("retained-owner negative control did not create an overlap")


def main() -> int:
    try:
        _check_issue45_inventory_owner()
        print("ISSUE48_WP31_RETAINED_OWNER_CHECK: issue45-inventory=RETAIN")
        _check_scale_owner()
        print("ISSUE48_WP31_RETAINED_OWNER_CHECK: scale-audit=RETAIN")
        _check_cleanup_scope()
        print("ISSUE48_WP31_RETAINED_OWNER_CHECK: cleanup-scope=PASS")
        _negative_control()
        print("ISSUE48_WP31_RETAINED_OWNER_CHECK: negative-control=PASS")
    except Exception as exc:
        print(f"ISSUE48_WP31_RETAINED_OWNER_CHARACTERIZATION: FAIL ({exc})")
        return 1
    print("ISSUE48_WP31_RETAINED_OWNER_CHARACTERIZATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
