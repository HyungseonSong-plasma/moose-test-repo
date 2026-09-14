#!/usr/bin/env python3
"""Compatibility wrapper for the Issue #224 R2 science-profile qualifier.

The canonical MOOSE parameter helper preserves quotes on enum-like values such
as execute_on = 'FINAL'.  The original qualifier compared that raw spelling to
FINAL and therefore failed P0 before any physical case ran.  This wrapper keeps
the experiment implementation unchanged and normalizes only that structural
self-test comparison.
"""
from __future__ import annotations

from experiments.Issue224_science_profiles import run as impl
from physics_harness.adapters.moose import parameters as mp

_ORIGINAL_SELF_TEST = impl.self_test


def _normalized_self_test():
    result = _ORIGINAL_SELF_TEST()
    replay, _ = impl.build_profile("DIAGNOSTIC_REPLAY")
    raw = mp.get_parameter(replay, "Outputs", "execute_on")
    normalized = (raw or "").strip().strip("'\"")
    result["checks"]["replay_output_final"] = normalized == "FINAL"
    result["replay_output_execute_on_raw"] = raw
    result["replay_output_execute_on_normalized"] = normalized
    result["failed_checks"] = sorted(k for k, ok in result["checks"].items() if not ok)
    result["status"] = "PASS" if not result["failed_checks"] else "FAIL"
    return result


impl.self_test = _normalized_self_test


if __name__ == "__main__":
    raise SystemExit(impl.main())
