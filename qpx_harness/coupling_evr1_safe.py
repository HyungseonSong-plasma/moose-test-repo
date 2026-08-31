"""Compatibility adapter for Issue #31 EVR1 deterministic physics CSV selection.

Issue31 scientific CSV-selection semantics live in ``recipes.issue31_coupling``.
This adapter preserves the historical ``coupling-evr1`` CLI route while the
legacy EVR1 runtime orchestration remains in ``qpx_harness.coupling_evr1``.
"""

from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path
from typing import Iterable

from recipes import issue31_coupling as recipe

from . import coupling_evr1 as base


CouplingEVR1Error = base.CouplingEVR1Error


def physics_csv(case_dir: Path, *, monolithic: bool) -> tuple[Path, dict[str, str]]:
    """Use canonical recipe selection while preserving the legacy error contract."""
    try:
        return recipe.physics_csv(case_dir, monolithic=monolithic)
    except recipe.Issue31CouplingError as exc:
        raise CouplingEVR1Error(str(exc)) from exc


def self_test() -> int:
    try:
        if base.self_test():
            raise AssertionError("base Issue31 EVR1 self-test failed")

        common = {
            "time": "1e-4",
            "r29_ne_min": "1e16",
            "r29_ne_max": "1e16",
            "r29_charge_min": "-1",
            "r29_charge_max": "1",
            "r29_charge_integral": "0",
            "r29_heavy_charge_number_integral": "0",
            "r29_electron_charge_number_integral": "0",
            "r29_sum_w_min": "1",
            "r29_sum_w_max": "1",
        }
        for species in recipe.SPECIES:
            common[f"r29_w_{species}_min"] = "0.01"
            common[f"r29_w_{species}_max"] = "0.12"
        common.update(
            {
                "r29_phi_min": "-1",
                "r29_phi_max": "1",
                "r29_phi_integral": "0",
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fieldnames = list(common)
            for name in ("input_out_r29_csv.csv", "input_out.csv"):
                with (root / name).open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerow(common)
            path, row = physics_csv(root, monolithic=True)
            if path.name != "input_out.csv":
                raise AssertionError(f"default CSV was not preferred: {path}")
            if row["time"] != "1e-4":
                raise AssertionError("positive solved row selection failed")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (root / "named_only.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(common))
                writer.writeheader()
                writer.writerow(common)
            path, _ = physics_csv(root, monolithic=True)
            if path.name != "named_only.csv":
                raise AssertionError("named-only deterministic fallback failed")

        with tempfile.TemporaryDirectory() as tmp:
            try:
                physics_csv(Path(tmp), monolithic=False)
            except CouplingEVR1Error:
                pass
            else:
                raise AssertionError("missing-CSV error translation was not preserved")
    except Exception as exc:
        print(f"ISSUE31_EVR1_SAFE_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE31_EVR1_SAFE_SELFTEST: PASS")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    args = list(argv) if argv is not None else list(sys.argv[1:])
    if "--self-test" in args:
        return self_test()

    original_physics_csv = base._physics_csv
    base._physics_csv = physics_csv
    try:
        return base.main(args)
    finally:
        base._physics_csv = original_physics_csv


if __name__ == "__main__":
    raise SystemExit(main())
