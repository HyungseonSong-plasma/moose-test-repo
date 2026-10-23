"""Regression checks for the archived Issue 403 four-gate diagnostic.

These tests use synthetic metadata only; they are not new 100-us simulations.
"""
from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "experiments/Issue395_powered_chemistry_ladder/issue397_four_checks.py"


def load_diagnostic():
    spec = importlib.util.spec_from_file_location("issue403_four_gate_diagnostics", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_evidence(root: Path, *, power: int, controlled: float, drive: float):
    root.joinpath("run").mkdir()
    root.joinpath("d1_native").mkdir()
    (root / "runtime.log").write_text("maxwell_t60: converged\n", encoding="utf-8")
    with (root / "run/plasma.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=[
            "time", "P_rf_scaled_W_t6", "P_abs_maxwell_t6", "rf_drive_scale_t6"
        ])
        writer.writeheader()
        writer.writerow({
            "time": "0.0001", "P_rf_scaled_W_t6": str(controlled),
            "P_abs_maxwell_t6": str(power), "rf_drive_scale_t6": str(drive),
        })
    (root / "d1_native/d1_native_summary.json").write_text(
        json.dumps({
            "status": "D1_NATIVE_DIAGNOSTIC_INTEGRITY_PASS",
            "wafer_faces": 27, "native_points": 461, "final_time_us": 100.0,
            "current_species_sum_rel_rms": 0.0,
            "surface_charge_balance_rel_rms": 0.0,
        }) + "\n",
        encoding="utf-8",
    )


class Issue403FourChecksTests(unittest.TestCase):
    def test_800w_normal_controlled_case_passes_all_gates(self):
        inspector = load_diagnostic().inspect
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_evidence(root, power=800, controlled=802.0, drive=2.5)
            result = inspector(root, 800, "PASS", "PASS", "synthetic-head")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual({v["status"] for v in result["checks"].values()}, {"PASS"})

    def test_1000w_pid_saturation_does_not_erase_numerical_convergence(self):
        inspector = load_diagnostic().inspect
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_evidence(root, power=1000, controlled=984.812, drive=3.0)
            result = inspector(root, 1000, "PASS", "PASS", "synthetic-head")
        self.assertEqual(result["status"], "NOT_PASS")
        gates = result["checks"]
        self.assertEqual(gates["maxwell_convergence"]["status"], "PASS")
        self.assertEqual(gates["historical_58ns"]["status"], "PASS")
        self.assertEqual(gates["physical_integrity_100us"]["status"], "PASS")
        self.assertEqual(gates["rf_power_and_PID"]["status"], "FAIL")
        self.assertTrue(gates["rf_power_and_PID"]["original_PID_cap_reached"])

    def test_missing_runtime_is_never_accepted_as_success(self):
        inspector = load_diagnostic().inspect
        with tempfile.TemporaryDirectory() as td:
            result = inspector(Path(td), 900, "UNKNOWN", "UNKNOWN", "synthetic-head")
        self.assertEqual(result["status"], "NOT_PASS")
        self.assertEqual(result["checks"]["rf_power_and_PID"]["status"], "INCOMPLETE")
        self.assertEqual(result["checks"]["physical_integrity_100us"]["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
