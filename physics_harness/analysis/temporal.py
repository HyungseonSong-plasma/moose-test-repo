"""Canonical temporal CSV normalization and trajectory observation."""

from __future__ import annotations

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


def find_temporal_csv(
    case_dir: Path,
    *,
    preferred_name: str = "input_out.csv",
    time_column: str = "time",
) -> Path | None:
    """Find the first readable CSV containing ``time_column`` without mutating it."""
    case_dir = Path(case_dir)
    preferred = case_dir / preferred_name
    candidates = [preferred] if preferred.is_file() else []
    candidates.extend(
        path for path in sorted(case_dir.glob("*.csv")) if path != preferred
    )
    for path in candidates:
        try:
            with path.open(newline="") as handle:
                reader = csv.DictReader(handle)
                if time_column in (reader.fieldnames or []):
                    return path
        except (OSError, csv.Error):
            continue
    return None


def observe_temporal_csv(
    source: Path,
    *,
    time_column: str = "time",
    physical_time_floor: float = 0.0,
) -> dict[str, object]:
    """Observe positive-time trajectory facts from one temporal CSV.

    Malformed individual time values are ignored so this function reports the
    mechanically observable trajectory without assigning a validation decision.
    The source file is never modified.
    """
    source = Path(source)
    times: list[float] = []
    try:
        with source.open(newline="") as handle:
            for row in csv.DictReader(handle):
                try:
                    value = float(row[time_column])
                except (KeyError, TypeError, ValueError):
                    continue
                if math.isfinite(value) and value > physical_time_floor:
                    times.append(value)
    except (OSError, csv.Error):
        return {"physical_rows": 0, "csv_status": "UNREADABLE_TIME_CSV"}

    observation: dict[str, object] = {
        "physical_rows": len(times),
        "csv": str(source),
        "csv_status": "PASS",
    }
    if not times:
        return observation

    times.sort()
    dts = [times[0]] + [b - a for a, b in zip(times, times[1:])]
    finite_positive_dts = [
        value for value in dts if math.isfinite(value) and value > 0.0
    ]
    observation["first_time"] = times[0]
    observation["final_time"] = times[-1]
    if finite_positive_dts:
        observation["actual_dt_min"] = min(finite_positive_dts)
        observation["actual_dt_max"] = max(finite_positive_dts)
    return observation


def observe_case_trajectory(
    case_dir: Path,
    *,
    preferred_name: str = "input_out.csv",
    time_column: str = "time",
    physical_time_floor: float = 0.0,
) -> dict[str, object]:
    """Find and observe one temporal CSV in ``case_dir``.

    The returned status vocabulary is mechanical and intentionally contains no
    experiment, issue, or physics classification.
    """
    source = find_temporal_csv(
        case_dir,
        preferred_name=preferred_name,
        time_column=time_column,
    )
    if source is None:
        return {"physical_rows": 0, "csv_status": "MISSING_TIME_CSV"}
    return observe_temporal_csv(
        source,
        time_column=time_column,
        physical_time_floor=physical_time_floor,
    )


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

    The source file is never modified.
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

    with source.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {source}")
        if time_column not in reader.fieldnames:
            raise ValueError(
                f"CSV {source} has no time column {time_column!r}; "
                f"columns={reader.fieldnames}"
            )
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    if not rows:
        raise ValueError(f"CSV has no data rows: {source}")

    classified = []
    previous_t = None
    initialization_count = 0
    physical_count = 0

    for row_number, row in enumerate(rows, start=2):
        t = _as_float(row[time_column], field=time_column, row_number=row_number)
        if previous_t is not None and t < previous_t - time_tol:
            raise ValueError(
                f"row {row_number}: non-monotone time: {t} follows {previous_t}"
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
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
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
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        source = tmp / "raw.csv"
        source.write_text(
            "time,w\n"
            "0,0\n"
            "0.1,0.90909090909091\n"
            "0.2,0.83333333333333\n"
        )

        physical = tmp / "physical.csv"
        summary = normalize_temporal_csv(
            source,
            physical,
            initial_row_policy="exclude_observation",
        )
        rows = list(csv.DictReader(physical.open(newline="")))
        c1 = summary["initialization_rows"] == 1
        c2 = len(rows) == 2 and float(rows[0]["time"]) == 0.1

        include = tmp / "include.csv"
        summary2 = normalize_temporal_csv(
            source,
            include,
            initial_row_policy="include_as_physics",
        )
        rows2 = list(csv.DictReader(include.open(newline="")))
        c3 = summary2["initialization_rows"] == 0 and len(rows2) == 3

        bad = tmp / "bad.csv"
        bad.write_text("time,w\n0.2,1\n0.1,1\n")
        try:
            normalize_temporal_csv(
                bad,
                tmp / "bad_out.csv",
                initial_row_policy="exclude_observation",
            )
            c4 = False
        except ValueError:
            c4 = True

        case_dir = tmp / "case"
        case_dir.mkdir()
        alternate = case_dir / "alternate.csv"
        alternate.write_text("time,value\n0,0\n0.1,1\n0.2,1\n")
        preferred = case_dir / "input_out.csv"
        preferred.write_text(
            "time,value\n"
            "0,0\n"
            "0.1,1\n"
            "bad,ignored\n"
            "0.2,1\n"
            "0.4,1\n"
        )
        found = find_temporal_csv(case_dir)
        observed = observe_case_trajectory(case_dir)
        c5 = found == preferred
        c6 = (
            observed.get("physical_rows") == 3
            and observed.get("csv") == str(preferred)
            and observed.get("csv_status") == "PASS"
            and observed.get("first_time") == 0.1
            and observed.get("final_time") == 0.4
            and observed.get("actual_dt_min") == 0.1
            and observed.get("actual_dt_max") == 0.2
        )

        missing_dir = tmp / "missing"
        missing_dir.mkdir()
        c7 = observe_case_trajectory(missing_dir) == {
            "physical_rows": 0,
            "csv_status": "MISSING_TIME_CSV",
        }

        no_time = missing_dir / "other.csv"
        no_time.write_text("value\n1\n")
        c8 = find_temporal_csv(missing_dir) is None

        initial_only = missing_dir / "input_out.csv"
        initial_only.write_text("time,value\n0,0\n")
        c9 = observe_case_trajectory(missing_dir) == {
            "physical_rows": 0,
            "csv": str(initial_only),
            "csv_status": "PASS",
        }

    ok = c1 and c2 and c3 and c4 and c5 and c6 and c7 and c8 and c9
    print("TEMPORAL_CSV_SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1
