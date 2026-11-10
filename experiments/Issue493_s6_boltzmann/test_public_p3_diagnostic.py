#!/usr/bin/env python3
"""Unit regressions for Issue493 bounded B diagnostic policy (offline, no Docker)."""
from __future__ import annotations

import copy
import unittest

import check_public_p3_diagnostic as validator


def valid_report() -> dict:
    return {
        "schema": "issue493_public_p3_native_v2",
        "mode": "diagnostic",
        "case": "417",
        "source_sha": validator.EXPECTED_SOURCE,
        "candidate_sha": validator.EXPECTED_CANDIDATE,
        "oci_image": validator.EXPECTED_OCI,
        "P0": "PASS", "P1": "PASS", "P2": "HOLD", "P3": "HOLD",
        "P4": "NOT_RUN", "science": "SCIENCE_HOLD",
        "p2_passed_arms": ["B"], "p2_not_run_arms": ["C"],
        "variants": {
            "B": {
                "P2": "PASS", "P3": "HOLD",
                "timeout_budget_seconds": 600,
                "timed_out": True, "exit_code": None, "termination": "TIMEOUT",
                "reason": "P3_DIAGNOSTIC_BUDGET_END", "wall_seconds": 600.19,
                "last_reported_step": None, "heartbeat_samples": 10,
                "native_log_bytes": 9999,
            },
            "C": {"P2": "NOT_RUN", "P3": "NOT_RUN"},
        },
    }


class DiagnosticEvidenceTests(unittest.TestCase):
    def test_expected_timeout_is_valid_and_p3_remains_hold(self):
        safe = validator.validate(valid_report(), "417")
        self.assertEqual(safe["p3"], "HOLD")
        self.assertEqual(safe["p4"], "NOT_RUN")
        self.assertIsNone(safe["last_reported_step"])

    def test_early_solver_failure_still_diagnostic_not_science(self):
        report = valid_report()
        report["variants"]["B"].update({
            "P3": "FAIL", "timed_out": False, "exit_code": 2,
            "termination": "EXIT", "reason": "P3_SOLVER_NONZERO",
            "wall_seconds": 42.1,
        })
        safe = validator.validate(report, "417")
        self.assertEqual(safe["b_status"], "FAIL")
        self.assertEqual(safe["p3"], "HOLD")

    def test_reject_false_pass_unpinned_sources_and_c_execution(self):
        base = valid_report()
        for patch in (
            ("P3", "PASS"),
            ("P4", "PASS"),
            ("science", "ACCEPTED"),
            ("source_sha", "changed"),
            ("mode", "full"),
        ):
            report = copy.deepcopy(base)
            report[patch[0]] = patch[1]
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validator.validate(report, "417")
        report = copy.deepcopy(base)
        report["variants"]["C"]["P2"] = "PASS"
        with self.assertRaises(ValueError):
            validator.validate(report, "417")

    def test_no_fabricated_exit_code_on_timeout(self):
        report = valid_report()
        report["variants"]["B"]["exit_code"] = 127
        with self.assertRaises(ValueError):
            validator.validate(report, "417")

    def test_no_budget_overrun(self):
        report = valid_report()
        report["variants"]["B"]["timeout_budget_seconds"] = 8100
        with self.assertRaises(ValueError):
            validator.validate(report, "417")


if __name__ == "__main__":
    unittest.main(verbosity=2)
