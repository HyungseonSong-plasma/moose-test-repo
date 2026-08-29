"""Issue #43 fast-plasma discriminator classification guard.

v3 enforces CORE-16 execution contracts at P1/P3.  This adapter prevents the
legacy v2 scientific classifier from re-labeling an ontology/construction failure
as an electron/Poisson physics failure and ensures the process exit code remains
non-zero for that class.
"""

from __future__ import annotations

import argparse
from typing import Any

from . import fast_plasma_relaxation_v2 as v2
from . import fast_plasma_relaxation_v3 as v3


_RAW_CLASSIFY = v2.classify
_LAST_DECISION: dict[str, Any] | None = None


def _harness_decision(label: str, case: dict[str, Any] | None) -> dict[str, Any] | None:
    if case is None or case.get("class") != "HARNESS_OR_CONSTRUCTION_FAIL":
        return None
    contract = case.get("execution_contract_p3") or case.get("execution_contract_p1")
    decision: dict[str, Any] = {
        "class": "HARNESS_OR_CONSTRUCTION_FAIL",
        "reason": f"{label} failed execution/ontology conformance before physics classification",
        "failed_case": label,
    }
    if isinstance(contract, dict):
        decision["contract_status"] = contract.get("status")
        decision["contract_blockers"] = contract.get("blockers")
    return decision


def classify(
    known_good: dict[str, Any],
    electron_300k: dict[str, Any] | None,
    oneway: dict[str, Any] | None,
    feedback_base: dict[str, Any] | None,
    feedback_small: dict[str, Any] | None,
    feedback_large: dict[str, Any] | None,
    tau_dr: float,
) -> dict[str, Any]:
    global _LAST_DECISION

    for label, case in (
        ("electron_300K", electron_300k),
        ("oneway_e_to_phi", oneway),
        ("feedback_base", feedback_base),
        ("feedback_small", feedback_small),
        ("feedback_large", feedback_large),
    ):
        guarded = _harness_decision(label, case)
        if guarded is not None:
            _LAST_DECISION = guarded
            return guarded

    decision = _RAW_CLASSIFY(
        known_good,
        electron_300k,
        oneway,
        feedback_base,
        feedback_small,
        feedback_large,
        tau_dr,
    )
    _LAST_DECISION = decision
    return decision


def _install() -> None:
    v2.classify = classify


def self_test() -> int:
    try:
        if v3.self_test() != 0:
            raise AssertionError("v3 self-test failed")
        kge = {"class": "P3_PASS", "canonical_checker": {"status": "PASS"}}
        harness = {
            "class": "HARNESS_OR_CONSTRUCTION_FAIL",
            "execution_contract_p1": {
                "status": "HOLD",
                "blockers": [{"id": "dt-above-dtmin"}],
            },
        }
        decision = classify(kge, harness, None, None, None, None, 1.0e-12)
        if decision.get("class") != "HARNESS_OR_CONSTRUCTION_FAIL":
            raise AssertionError("construction failure was relabeled as physics failure")
        good = {"class": "P3_PASS", "analysis": {"status": "PASS"}}
        decision = classify(kge, good, good, good, None, good, 1.0e-12)
        if decision.get("class") != "FEEDBACK_IMPLICIT_COUPLING_RECOVERS_NEAR_TAU_DR":
            raise AssertionError("positive scientific classification path changed")
    except Exception as exc:
        print(f"ISSUE43_FAST_V4_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE43_FAST_V4_SELFTEST: PASS")
    return 0


def main(argv: list[str] | None = None) -> int:
    global _LAST_DECISION
    args = list(argv or [])
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--self-test", action="store_true")
    known, _ = parser.parse_known_args(args)
    if known.self_test:
        return self_test()
    if self_test() != 0:
        return 1

    _LAST_DECISION = None
    _install()
    rc = v3.main(args)
    if (
        _LAST_DECISION is not None
        and _LAST_DECISION.get("class") == "HARNESS_OR_CONSTRUCTION_FAIL"
    ):
        return 2
    return rc


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
