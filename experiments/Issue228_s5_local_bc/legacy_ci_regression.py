#!/usr/bin/env python3
"""Regression for evidence-valid scientific rejection semantics.

Consumes prior Issue-228 summaries that historically exited nonzero solely because
`status == PHYSICS_MODEL_FAIL`.  The regression passes only when the archived run
actually completed P2/runtime/analysis and therefore constitutes valid scientific
evidence under CI semantics v2.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def classify(path: Path) -> dict:
    s = json.loads(path.read_text(encoding="utf-8"))
    p2_ok = int(s.get("p2", {}).get("returncode", 1)) == 0
    rt = s.get("runtime", {})
    runtime_ok = int(rt.get("returncode", 1)) == 0 and not bool(rt.get("timed_out", True))
    analysis_ok = all(k in s for k in ("phi_min_V", "phi_max_V", "hotspots", "acceptance_gates"))
    scientific_rejection = s.get("status") == "PHYSICS_MODEL_FAIL"
    evidence_valid = p2_ok and runtime_ok and analysis_ok
    return {
        "source": str(path),
        "legacy_status": s.get("status"),
        "p2_ok": p2_ok,
        "runtime_ok": runtime_ok,
        "analysis_ok": analysis_ok,
        "scientific_rejection": scientific_rejection,
        "evidence_valid_v2": evidence_valid,
        "ci_exit_v2": 0 if evidence_valid else 1,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--summary", type=Path, action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    rows = [classify(x) for x in a.summary]
    ok = all(r["scientific_rejection"] and r["evidence_valid_v2"] and r["ci_exit_v2"] == 0 for r in rows)
    payload = {
        "status": "PASS" if ok else "VALIDATOR_SELFTEST_FAIL",
        "rule": "historical PHYSICS_MODEL_FAIL with valid evidence must be green under CI semantics v2",
        "cases": rows,
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
