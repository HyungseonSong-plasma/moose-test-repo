#!/usr/bin/env python3
"""Issue #395 RF+EI02 elastic driver with lagged standard-MOOSE PID power feedback."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import run_rf_elastic_constant_power as driver

# Constant absorbed power is now controlled by accepted-step feedback, not by
# trial/reject iteration.  Small transient power errors are allowed while a
# 2% guardrail still catches loss of control.
driver.POWER_GATE = 2.0e-2


def analysis_path_from_argv() -> Path | None:
    try:
        return Path(sys.argv[sys.argv.index("--analysis") + 1]).resolve()
    except (ValueError, IndexError):
        return None


def main() -> int:
    rc = driver.main()
    path = analysis_path_from_argv()
    if path and path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        pc = data.setdefault("power_control", {})
        pc.update(
            {
                "feedback_controller": "MOOSE PIDTransientControl",
                "feedback_mode": "accepted TIMESTEP_END error applied to following timestep",
                "trial_step_iteration": False,
                "K_proportional_per_W": -1.0e-3,
                "K_integral": 0.0,
                "K_derivative": 0.0,
                "pid_scale_bounds": [0.5, 1.5],
                "hard_relative_power_guardrail": driver.POWER_GATE,
                "error_definition": "P_absorbed - 1000 W",
                "feedback_sign": "positive power error decreases next-step RF multiplier",
            }
        )
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
