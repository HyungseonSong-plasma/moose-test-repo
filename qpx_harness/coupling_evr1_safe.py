"""Safety adapter for Issue #31 EVR1 runtime-output selection.

MOOSE may emit both the default CSV and an explicitly named CSV output from the
same input.  The base EVR1 checker needs one deterministic r29-observable CSV;
it must not fail merely because both equivalent output files exist.
"""

from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from . import coupling_evr1 as base


CouplingEVR1Error = base.CouplingEVR1Error


def physics_csv(case_dir: Path, *, monolithic: bool) -> tuple[Path, dict[str, str]]:
    required = {
        "time",
        "r29_ne_min",
        "r29_ne_max",
        "r29_charge_min",
        "r29_charge_max",
        "r29_charge_integral",
        "r29_heavy_charge_number_integral",
        "r29_electron_charge_number_integral",
        "r29_sum_w_min",
        "r29_sum_w_max",
    }
    for species in base.SPECIES:
        required.add(f"r29_w_{species}_min")
        required.add(f"r29_w_{species}_max")
    if monolithic:
        required.update({"r29_phi_min", "r29_phi_max", "r29_phi_integral"})

    candidates: list[tuple[Path, list[dict[str, str]]]] = []
    for path in sorted(case_dir.glob("*.csv")):
        try:
            with path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, csv.Error):
            continue
        if not rows:
            continue
        if required.issubset(rows[0].keys()):
            candidates.append((path, rows))

    if not candidates:
        raise CouplingEVR1Error(
            "no runtime physics CSV contains the required r29 observables"
        )

    # Prefer the canonical default output when present.  If a MOOSE version or
    # case naming policy uses only named CSV outputs, use lexical order so the
    # choice remains deterministic and recorded in the evidence.
    preferred = [item for item in candidates if item[0].name == "input_out.csv"]
    path, rows = preferred[0] if preferred else candidates[0]

    physical = [row for row in rows if base._float(row, "time") > 1e-15]
    if not physical:
        raise CouplingEVR1Error(f"no positive solved-time row in {path}")
    return path, physical[-1]


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
        for species in base.SPECIES:
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
    except Exception as exc:
        print(f"ISSUE31_EVR1_SAFE_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE31_EVR1_SAFE_SELFTEST: PASS")
    return 0


def _activate() -> None:
    base._physics_csv = physics_csv
    base.self_test = self_test


def main(argv: Iterable[str] | None = None) -> int:
    args = list(argv) if argv is not None else list(sys.argv[1:])
    if "--self-test" in args:
        return self_test()
    base._physics_csv = physics_csv
    return base.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
