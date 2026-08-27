#!/usr/bin/env python3

"""General temporal CSV normalization for QPX/MOOSE validation.

The raw MOOSE CSV is preserved.  A separate physical-only CSV is generated
when a manifest explicitly declares that initialization-stage rows are
observation-only and must not participate in physical acceptance metrics.

This module deliberately does *not* silently drop the first row.  The row
policy must be declared by the test manifest.
"""

from __future__ import annotations

import argparse
import csv
import math
import tempfile
from pathlib import Path


VALID_INITIAL_POLICIES = {
    "exclude_observation",
    "include_as_physics",
}


def _as_float(value: str, *, field: str, row_number: int) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"row {row_number}: temporal field {field!r} is not numeric: {value!r}"
        ) from exc
    if not math.isfinite(out):
        raise ValueError(
            f"row {row_number}: temporal field {field!r} is not finite: {value!r}"
        )
    return out


def normalize_temporal_csv(
    source: Path,
    output: Path,
    *,
    time_column: str = "time",
    initial_row_policy: str,
    initial_time: float = 0.0,
    time_tol: float = 1.0e-15,
    require_physical_rows: bool = True,
) -> dict:
    """Normalize one temporal CSV according to an explicit row policy.

    Returns a summary dictionary.  The source file is never modified.
    """

    if initial_row_policy not in VALID_INITIAL_POLICIES:
        raise ValueError(
            f"unsupported initial_row_policy={initial_row_policy!r}; "
            f"expected one of {sorted(VALID_INITIAL_POLICIES)}"
        )
    if time_tol < 0:
        raise ValueError("time_tol must be non-negative")
    if not source.is_file():
        raise FileNotFoundError(source)

    with source.open(newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {source}")
        if time_column not in reader.fieldnames:
            raise ValueError(
                f"CSV {source} has no time column {time_column!r}; "
                f"columns={reader.fieldnames}"
            )
        rows = list(reader)

    if not rows:
        raise ValueError(f"CSV has no data rows: {source}")

    classified = []
    previous_t = None
    initialization_count = 0
    physical_count = 0

    for i, row in enumerate(rows, start=2):
        t = _as_float(row[time_column], field=time_column, row_number=i)
        if previous_t is not None and t < previous_t - time_tol:
            raise ValueError(
                f"row {i}: non-monotone time: {t} follows {previous_t}"
            )
        previous_t = t

        is_initial = abs(t - initial_time) <= time_tol
        if is_initial and initial_row_policy == "exclude_observation":
            initialization_count += 1
            continue

        physical_count += 1
        classified.append(row)

    if require_physical_rows and physical_count == 0:
        raise ValueError("no physical rows remain after temporal classification")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=reader.fieldnames)
        writer.writeheader()
        writer.writerows(classified)

    return {
        "source_rows": len(rows),
        "initialization_rows": initialization_count,
        "physical_rows": physical_count,
        "initial_row_policy": initial_row_policy,
        "source": str(source),
        "output": str(output),
    }


def normalize_from_manifest(case_dir: Path, spec: dict) -> dict:
    required = ["source", "physical", "initial_row_policy"]
    missing = [key for key in required if key not in spec]
    if missing:
        raise ValueError(f"temporal_csv manifest entry missing keys: {missing}")

    return normalize_temporal_csv(
        case_dir / spec["source"],
        case_dir / spec["physical"],
        time_column=spec.get("time_column", "time"),
        initial_row_policy=spec["initial_row_policy"],
        initial_time=float(spec.get("initial_time", 0.0)),
        time_tol=float(spec.get("time_tol", 1.0e-15)),
        require_physical_rows=bool(spec.get("require_physical_rows", True)),
    )


def self_test() -> int:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        src = td / "raw.csv"
        src.write_text(
            "time,w\n"
            "0,0\n"
            "0.1,0.90909090909091\n"
            "0.2,0.83333333333333\n"
        )

        physical = td / "physical.csv"
        summary = normalize_temporal_csv(
            src,
            physical,
            initial_row_policy="exclude_observation",
        )
        rows = list(csv.DictReader(physical.open(newline="")))
        c1 = summary["initialization_rows"] == 1
        c2 = len(rows) == 2 and float(rows[0]["time"]) == 0.1

        include = td / "include.csv"
        summary2 = normalize_temporal_csv(
            src,
            include,
            initial_row_policy="include_as_physics",
        )
        rows2 = list(csv.DictReader(include.open(newline="")))
        c3 = summary2["initialization_rows"] == 0 and len(rows2) == 3

        bad = td / "bad.csv"
        bad.write_text("time,w\n0.2,1\n0.1,1\n")
        try:
            normalize_temporal_csv(
                bad,
                td / "bad_out.csv",
                initial_row_policy="exclude_observation",
            )
            c4 = False
        except ValueError:
            c4 = True

    ok = c1 and c2 and c3 and c4
    print("TEMPORAL_CSV_SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?")
    ap.add_argument("--output")
    ap.add_argument("--time-column", default="time")
    ap.add_argument(
        "--initial-row-policy",
        choices=sorted(VALID_INITIAL_POLICIES),
    )
    ap.add_argument("--initial-time", type=float, default=0.0)
    ap.add_argument("--time-tol", type=float, default=1.0e-15)
    ap.add_argument("--allow-no-physical-rows", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if not args.source or not args.output or not args.initial_row_policy:
        ap.error(
            "source, --output, and --initial-row-policy are required unless --self-test"
        )

    summary = normalize_temporal_csv(
        Path(args.source),
        Path(args.output),
        time_column=args.time_column,
        initial_row_policy=args.initial_row_policy,
        initial_time=args.initial_time,
        time_tol=args.time_tol,
        require_physical_rows=not args.allow_no_physical_rows,
    )
    print("TEMPORAL_CSV_NORMALIZE: PASS")
    for key in (
        "source_rows",
        "initialization_rows",
        "physical_rows",
        "initial_row_policy",
        "output",
    ):
        print(f"{key.upper()}={summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
