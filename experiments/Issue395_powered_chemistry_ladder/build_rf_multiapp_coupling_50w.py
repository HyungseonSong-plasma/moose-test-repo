#!/usr/bin/env python3
"""Build the Issue #395 continuous plasma<->Maxwell MultiApp coupling at 50 W.

This variant preserves the accepted-step parent-power PID architecture and
initializes the Maxwell drive from the validated 1000 W calibration using
square-root power scaling. Chemistry overlays are supplied separately.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import build_rf_multiapp_coupling as base

TARGET_W = 50.0
KP = -5.0e-4
INITIAL_DRIVE = base.BASELINE_1000W_DRIVE * math.sqrt(TARGET_W / 1000.0)
MIN_DRIVE = 0.5
MAX_DRIVE = 6.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", type=Path, required=True)
    ap.add_argument("--parent-overlay", type=Path, required=True)
    ap.add_argument("--child-overlay", type=Path, required=True)
    ap.add_argument("--child-input", type=Path, required=True)
    a = ap.parse_args()

    base.INITIAL_DRIVE = INITIAL_DRIVE

    x, mu_n = base.v2.v1.table(a.table)
    child_path = a.child_input.name
    parent = base.build_parent(x, mu_n, child_path, TARGET_W, KP)
    parent = base.replace_once(
        parent,
        "    minimum_output_value = 3.0\n",
        f"    minimum_output_value = {MIN_DRIVE:.17g}\n",
        "50 W PID minimum drive",
    )
    parent = base.replace_once(
        parent,
        "    maximum_output_value = 12.0\n",
        f"    maximum_output_value = {MAX_DRIVE:.17g}\n",
        "50 W PID maximum drive",
    )
    child = base.build_child(x, mu_n)

    a.parent_overlay.write_text(parent, encoding="utf-8")
    a.child_overlay.write_text(child, encoding="utf-8")
    a.child_input.write_text(
        "!include ../Issue202_maxwell_scalar_fem_m0/rf_power.i\n"
        f"!include {a.child_overlay.name}\n",
        encoding="utf-8",
    )

    print(
        "ISSUE395_RF_MULTIAPP_50W_BUILD_PASS "
        f"target_W={TARGET_W:.9g} Kp={KP:.9g} initial_drive={INITIAL_DRIVE:.15g} "
        f"min_drive={MIN_DRIVE:.9g} max_drive={MAX_DRIVE:.9g} "
        "feedback_sensor=P_rf_raw_W_t6 parent=transient_plasma "
        "child=FullSolveMultiApp_Maxwell probe=false rollback=false recover=false"
    )


if __name__ == "__main__":
    main()
