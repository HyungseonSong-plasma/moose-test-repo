#!/usr/bin/env python3
"""Issue48 characterization for canonical owners retained outside retirement inventory."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CLEANUP_INVENTORY = ROOT / "tests" / "Issue48_qpx_harness_generality" / "cleanup_inventory.py"
RETAINED_OWNERS = {
    "performance/runner.py": (
        "Reusable QPX/MOOSE performance measurement core.",
        "def validate_experiment_manifest(",
        "def run_measurement(",
    ),
    "performance/smoke.py": (
        "Managed PF-1 BENCHMARK/PROFILE smoke execution.",
        "def build_smoke_manifest(",
        "def run_smoke_pair(",
    ),
    "analysis/performance/investigation.py": (
        "PF-3 performance investigation analyzer.",
        "def classify_bottleneck(",
        "def build_investigation_summary(",
    ),
    "performance/probes/transport.py": (
        "Direct-PerfGraph PF-3 transport probe backend.",
        "def instrument_source(",
        "def analyze_probe(",
    ),
}
CLI_ROUTES = {
    "performance/runner.py": '"measure": measure_main',
    "performance/smoke.py": '"measure-smoke": measure_smoke_main',
    "analysis/performance/investigation.py": '"investigate": investigate_main',
    "performance/probes/transport.py": '"transport-probe": transport_probe_main',
}


def _load_cleanup_inventory() -> ModuleType:
    spec = importlib.util.spec_from_file_location("issue48_cleanup_inventory", CLEANUP_INVENTORY)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load cleanup inventory module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _require_retained_excluded(candidates: set[str]) -> None:
    overlap = sorted(set(RETAINED_OWNERS) & candidates)
    if overlap:
        raise AssertionError(f"canonical retained owners re-entered retirement inventory: {overlap}")


def _check_owner_capabilities() -> None:
    for owner, markers in RETAINED_OWNERS.items():
        path = ROOT / "qpx_harness" / owner
        if not path.is_file():
            raise AssertionError(f"retained owner missing: {path}")
        text = path.read_text()
        missing = [marker for marker in markers if marker not in text]
        if missing:
            raise AssertionError(f"retained owner capability drift {owner}: missing={missing}")


def _check_cli_routes() -> None:
    cli = (ROOT / "qpx_harness" / "cli" / "app.py").read_text()
    missing = [owner for owner, marker in CLI_ROUTES.items() if marker not in cli]
    if missing:
        raise AssertionError(f"retained owner stable CLI route missing: {missing}")


def self_test() -> int:
    try:
        inventory = _load_cleanup_inventory()
        candidates = set(inventory.CLEANUP_CANDIDATES)
        _require_retained_excluded(candidates)
        _check_owner_capabilities()
        _check_cli_routes()

        # Negative control: the discriminator must reject a retained canonical
        # owner if a future edit accidentally puts it back into retirement inventory.
        try:
            _require_retained_excluded(candidates | {"performance/runner.py"})
        except AssertionError:
            pass
        else:
            raise AssertionError("retained-owner reinsertion negative control was accepted")
    except Exception as exc:
        print(f"ISSUE48_RETAINED_OWNER_DISPOSITION_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE48_RETAINED_OWNER_DISPOSITION_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
