#!/usr/bin/env python3
"""Build Issue #395 continuous plasma<->Maxwell MultiApp coupling for a target RF power.

This parameterized low-power builder preserves the same accepted-step PID feedback
used by the 10 W discriminator while allowing controlled power-scan cases.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import build_rf_multiapp_coupling as base

KP = -5.0e-4
MIN_DRIVE = 0.1
MAX_DRIVE = 3.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-w", type=float, required=True)
    ap.add_argument("--table", type=Path, required=True)
    ap.add_argument("--parent-overlay", type=Path, required=True)
    ap.add_argument("--child-overlay", type=Path, required=True)
    ap.add_argument("--child-input", type=Path, required=True)
    a = ap.parse_args()

    if a.target_w <= 0.0:
        raise SystemExit("--target-w must be positive")

    initial_drive = base.BASELINE_1000W_DRIVE * math.sqrt(a.target_w / 1000.0)
    base.INITIAL_DRIVE = initial_drive

    x, mu_n = base.v2.v1.table(a.table)
    child_path = a.child_input.name
    parent = base.build_parent(x, mu_n, child_path, a.target_w, KP)
    parent = base.replace_once(
        parent,
        "    minimum_output_value = 3.0\n",
        f"    minimum_output_value = {MIN_DRIVE:.17g}\n",
        "power-scan PID minimum drive",
    )
    parent = base.replace_once(
        parent,
        "    maximum_output_value = 12.0\n",
        f"    maximum_output_value = {MAX_DRIVE:.17g}\n",
        "power-scan PID maximum drive",
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
        "ISSUE395_RF_MULTIAPP_POWER_BUILD_PASS "
        f"target_W={a.target_w:.9g} Kp={KP:.9g} initial_drive={initial_drive:.15g} "
        f"min_drive={MIN_DRIVE:.9g} max_drive={MAX_DRIVE:.9g} "
        "feedback_sensor=P_rf_raw_W_t6 parent=transient_plasma "
        "child=FullSolveMultiApp_Maxwell probe=false rollback=false recover=false"
    )


if __name__ == "__main__":
    main()
