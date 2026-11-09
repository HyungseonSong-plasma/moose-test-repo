"""Regression checks for the trusted two-lane S6 numerical replay orchestrator.

No native solver, protected rate table, OCI container or workflow is launched.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
S6 = ROOT / "experiments" / "Issue402_plasma_dsl_g1"
CASES = ["S6-417-407-2069-H25", "S6-941-407-2069-H25"]
PASS = "S6_FULL_460_STEP_NATIVE_PARITY_PASS__SCIENCE_HOLD"


def load_gate():
    spec = importlib.util.spec_from_file_location(
        "issue402_s6_two_way_runner", S6 / "run_s6_full_native_parity.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(S6))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(S6))
    return module


def prepared(tmp_path):
    for case in CASES:
        (tmp_path / case).mkdir()
    return [{"case": case} for case in CASES]


def test_two_cases_overlap_and_return_in_fixed_order(tmp_path, monkeypatch):
    gate = load_gate()
    barrier = threading.Barrier(2)

    def native_stub(meta, source_root, binary, work, timeout_seconds, rtol, atol):
        # The first lane cannot proceed unless the second is active.
        barrier.wait(timeout=10)
        return {"case": meta["case"], "status": PASS, "science_acceptance": "HOLD"}

    monkeypatch.setattr(gate, "run_case", native_stub)
    results = gate.run_cases_two_way(
        prepared(tmp_path), tmp_path, tmp_path, tmp_path, 10, 1e-11, 1e-12)
    assert [r["case"] for r in results] == CASES
    assert all(r["status"] == PASS for r in results)
    assert all(json.loads((tmp_path / case / "native_parity_report.json").read_text())
               ["science_acceptance"] == "HOLD" for case in CASES)


def test_one_failed_lane_does_not_erase_other_and_cannot_pass(tmp_path, monkeypatch):
    gate = load_gate()
    barrier = threading.Barrier(2)

    def native_stub(meta, source_root, binary, work, timeout_seconds, rtol, atol):
        barrier.wait(timeout=10)
        if meta["case"] == CASES[0]:
            raise RuntimeError("PRIVATE_RATE_LOCATION_MUST_NOT_APPEAR")
        return {"case": meta["case"], "status": PASS, "science_acceptance": "HOLD"}

    monkeypatch.setattr(gate, "run_case", native_stub)
    results = gate.run_cases_two_way(
        prepared(tmp_path), tmp_path, tmp_path, tmp_path, 10, 1e-11, 1e-12)
    assert results[0]["status"] == "S6_FULL_NATIVE_PARITY_NOT_PROVEN"
    assert results[0]["failure_class"] == "RuntimeError"
    assert results[1]["status"] == PASS
    assert results[0]["science_acceptance"] == results[1]["science_acceptance"] == "HOLD"
    assert "PRIVATE_RATE_LOCATION_MUST_NOT_APPEAR" not in (
        tmp_path / CASES[0] / "native_parity_report.json").read_text()
    assert (tmp_path / CASES[1] / "native_parity_report.json").is_file()


def test_duplicate_case_is_rejected_before_dispatch(tmp_path, monkeypatch):
    gate = load_gate()
    called = []

    def native_stub(*args):
        called.append(True)

    monkeypatch.setattr(gate, "run_case", native_stub)
    with pytest.raises(ValueError, match="distinct S6"):
        gate.run_cases_two_way([{"case": CASES[0]}, {"case": CASES[0]}],
                               tmp_path, tmp_path, tmp_path, 10, 1e-11, 1e-12)
    assert not called
