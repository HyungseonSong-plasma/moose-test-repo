#!/usr/bin/env python3
"""Dependency-free P0 self-test for CI/evidence scientific-outcome semantics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def ci_exit_code(evidence_valid: bool, scientific_outcome: str) -> int:
    _ = scientific_outcome
    return 0 if evidence_valid else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    cases = {
        "supported_valid": (True, "HYPOTHESIS_SUPPORTED_STRONG", 0),
        "rejected_valid": (True, "HYPOTHESIS_NOT_SUPPORTED", 0),
        "negative_control_valid": (True, "REFERENCE_RESIDUAL_CONFIRMED", 0),
        "construction_invalid": (False, "HARNESS_OR_CONSTRUCTION_FAIL", 1),
        "solver_invalid": (False, "SOLVER_CONVERGENCE_FAIL", 1),
    }
    observed = {k: ci_exit_code(v[0], v[1]) for k, v in cases.items()}
    expected = {k: v[2] for k, v in cases.items()}
    ok = observed == expected
    payload = {
        "status": "PASS" if ok else "VALIDATOR_SELFTEST_FAIL",
        "dependency_free": True,
        "rule": "CI failure means invalid evidence; scientific rejection remains green",
        "observed": observed,
        "expected": expected,
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
