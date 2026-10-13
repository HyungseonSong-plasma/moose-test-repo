#!/usr/bin/env python3
"""Run Issue #395 A1 on the accepted continuous 0 -> 15 us topology.

The existing long-horizon driver is retained for the accepted 100 ns Maxwell
calibration and target-quadrature normalization.  Only its final production
launch is intercepted: the 100 ns recovery is replaced by a fresh continuous
0 -> 15 us TimeSequenceStepper run.  A standard MOOSE TimePeriod control in
the chemistry overlay keeps A1 source projections and RF heating disabled
through 100 ns, then enables them for the 100 -> 110 ns step.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

import run_a1_15us as legacy

TIME_TOL = 5.0e-15


def expected_times() -> np.ndarray:
    times = [0.0]
    times.extend(i * 1.0e-9 for i in range(1, 101))
    t = times[-1]
    times.extend(t + i * 1.0e-8 for i in range(1, 91))
    t = times[-1]
    times.extend(t + i * 1.0e-7 for i in range(1, 91))
    t = times[-1]
    times.extend(t + i * 1.0e-6 for i in range(1, 6))
    return np.asarray(times, dtype=float)


def arg_path(name: str) -> Path:
    try:
        i = sys.argv.index(name)
    except ValueError as exc:
        raise RuntimeError(f"missing required argument {name}") from exc
    return Path(sys.argv[i + 1]).resolve()


def clean_output_base(file_base: str) -> None:
    base = Path(file_base).resolve()
    base.parent.mkdir(parents=True, exist_ok=True)
    for path in base.parent.glob(base.name + "*"):
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def main() -> int:
    original_run = legacy.base.run
    production_intercepts = 0

    def run_continuous(cmd, log):
        nonlocal production_intercepts
        words = [str(x) for x in cmd]
        is_production = (
            "--recover" in words
            and "source_enable_t6=1" in words
            and any("a1_15us_full_icp.i" in x for x in words)
        )
        if not is_production:
            return original_run(cmd, log)

        production_intercepts += 1
        if production_intercepts != 1:
            raise RuntimeError("expected exactly one 15 us production launch")

        file_base_tokens = [x for x in words if x.startswith("Outputs/file_base=")]
        if len(file_base_tokens) != 1:
            raise RuntimeError("could not identify production Outputs/file_base")
        file_base = file_base_tokens[0].split("=", 1)[1]
        clean_output_base(file_base)

        fresh_cmd = [x for x in cmd if str(x) != "--recover"]
        print(
            "ISSUE395_A1_CONTINUOUS_PRODUCTION_LAUNCH "
            "restart_recover=false trajectory=0_to_15us"
        )
        return original_run(fresh_cmd, log)

    legacy.base.run = run_continuous
    rc = legacy.main()
    if rc != 0:
        return rc
    if production_intercepts != 1:
        raise RuntimeError("continuous production launch was not intercepted")

    output_dir = arg_path("--output-dir")
    analysis_path = arg_path("--analysis")
    state15 = output_dir / "A1_15us" / "state15us.e"
    ex = legacy.base.exodus(state15)
    actual = np.asarray(ex["times"], dtype=float)
    expected = expected_times()

    i100 = int(np.argmin(np.abs(actual - 1.0e-7)))
    first_dt = (
        float(actual[i100 + 1] - actual[i100])
        if i100 + 1 < len(actual)
        else float("nan")
    )
    time_grid_match = (
        len(actual) == len(expected)
        and bool(np.all(np.abs(actual - expected) <= TIME_TOL))
    )
    first_dt_match = (
        abs(float(actual[i100]) - 1.0e-7) <= TIME_TOL
        and abs(first_dt - 1.0e-8) <= TIME_TOL
    )

    report = json.loads(analysis_path.read_text(encoding="utf-8"))
    metrics = report.setdefault("metrics", {})
    metrics["continuous_production_no_recover"] = True
    metrics["time_grid_points"] = int(len(actual))
    metrics["accepted_time_grid_match"] = time_grid_match
    metrics["first_post_100ns_dt_s"] = first_dt
    report["production_integration_policy"] = (
        "single fresh 0-to-15 us TimeSequenceStepper run; no production recover"
    )

    failures = list(report.get("failures", []))
    if not time_grid_match:
        failures.append("accepted 15 us time grid mismatch")
    if not first_dt_match:
        failures.append("first post-100 ns step is not 10 ns")
    report["failures"] = failures
    report["status"] = "PASS" if not failures else "FAIL"
    report["classification"] = (
        "ISSUE395_A1_15US_CONTINUOUS_FROZEN_FIELD_SCREEN_PASS"
        if not failures
        else "ISSUE395_A1_15US_CONTINUOUS_FROZEN_FIELD_SCREEN_FAIL"
    )
    analysis_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
