#!/usr/bin/env python3
"""Oxygen24 two-stage MOOSE checkpoint smoke: [0,1,2] ns -> recover -> [3,4] ns.

No solver-state reconstruction from CSV. The genuine MOOSE _cp checkpoint is
mandatory. Exact neutral inlet, chemistry and RF overlays remain untouched.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path

END_2NS = 2e-9
END_4NS = 4e-9
STAGE1_GRID = (0.0, 1e-9, 2e-9)
STAGE2_GRID = (0.0, 1e-9, 2e-9, 3e-9, 4e-9)
OUTPUT_RE = re.compile(r"(?ms)^\[Outputs\]\n(?P<body>.*?)^\[\]\s*$")
EXEC_RE = re.compile(r"(?ms)^\[Executioner\]\n(?P<body>.*?)^\[\]\s*$")
END_RE = re.compile(r"(?m)^(\s*end_time\s*=\s*)[^#\n]+$")
SEQ_RE = re.compile(r"(?m)^(\s*time_sequence\s*=\s*)'[^']*'\s*$")

# Reference 2-ns solution of source commit 0fe03c1e5f6bf14385f51130a43dc4732f2608dc.
# Comparing the new first-stage solution proves that enabling checkpoints
# did not inadvertently alter neutral initialization or power-specific physics.
BASELINE_2NS = {
    400: {
        "n_O2_X_avg": 3.2187377479051e20,
        "n_O2_a_avg": 3.2197715142757e15,
        "n_O_3P_avg": 3.2200202344883e15,
        "n_O_1D_avg": 3.2188196567368e15,
        "ne_max": 1.1125652267094e15,
    },
    1000: {
        "n_O2_X_avg": 3.2187377465817e20,
        "n_O2_a_avg": 3.2198730374075e15,
        "n_O_3P_avg": 3.2200808692331e15,
        "n_O_1D_avg": 3.2188196567991e15,
        "ne_max": 1.1125663997292e15,
    },
}


def _one(pattern: re.Pattern[str], source: str, name: str) -> re.Match[str]:
    found = list(pattern.finditer(source))
    if len(found) != 1:
        raise ValueError(f"expected exactly one {name}, got {len(found)}")
    return found[0]


def _grid(source: str) -> tuple[float, list[float]]:
    body = _one(EXEC_RE, source, "Executioner").group("body")
    ends = list(END_RE.finditer(body))
    grids = list(SEQ_RE.finditer(body))
    if len(ends) != 1 or len(grids) != 1:
        raise ValueError("need unique end_time and time_sequence")
    return float(ends[0].group().split("=", 1)[1]), [
        float(value) for value in grids[0].group().split("'", 2)[1].split()
    ]


def _close(actual: float, target: float, label: str, rtol: float = 1e-8) -> None:
    if not math.isfinite(actual) or not math.isclose(actual, target, rel_tol=rtol, abs_tol=1e-17):
        raise ValueError(f"{label}: {actual!r} != {target!r}")


def verify_grid(source: str, stage: int) -> None:
    expected = STAGE1_GRID if stage == 1 else STAGE2_GRID
    end, values = _grid(source)
    _close(end, expected[-1], "end_time", 1e-12)
    if len(values) != len(expected):
        raise ValueError(f"expected {len(expected)} time values, got {len(values)}")
    for i, (actual, target) in enumerate(zip(values, expected)):
        _close(actual, target, f"time_sequence[{i}]", 1e-12)
    output = _one(OUTPUT_RE, source, "Outputs").group("body")
    if len(re.findall(r"(?m)^\s*checkpoint\s*=\s*true\s*$", output)) != 1:
        raise ValueError("no unique checkpoint = true in Outputs")


def enable_checkpoint(source: str) -> str:
    end, values = _grid(source)
    _close(end, END_2NS, "original 2ns end")
    if len(values) != 3:
        raise ValueError("must start with the exact two-step reference grid")
    for n, t in enumerate(STAGE1_GRID):
        _close(values[n], t, f"reference time {n}")
    block = _one(OUTPUT_RE, source, "Outputs")
    body = block.group("body")
    if re.search(r"(?m)^\s*checkpoint\s*=", body):
        raise ValueError("checkpoint already present; refuse duplicate output owner")
    updated = source[:block.start("body")] + "  checkpoint = true\n" + body + source[block.end("body"):]
    verify_grid(updated, 1)
    return updated


def extend_checkpoint(source: str) -> str:
    verify_grid(source, 1)
    match = _one(EXEC_RE, source, "Executioner")
    body = match.group("body")
    body = END_RE.sub(lambda m: m.group(1) + format(END_4NS, ".17g"), body, count=1)
    seq = " ".join("0" if time == 0 else format(time, ".17g") for time in STAGE2_GRID)
    body = SEQ_RE.sub(lambda m: m.group(1) + "'" + seq + "'", body, count=1)
    out = source[:match.start("body")] + body + source[match.end("body"):]
    verify_grid(out, 2)
    return out


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def verify_first(path: Path, power: int) -> dict[str, object]:
    rows = read_csv(path)
    if len(rows) != 3:
        raise ValueError(f"first-stage CSV must contain t=0,1,2ns; got {len(rows)} rows")
    for i, row in enumerate(rows):
        _close(float(row["time"]), STAGE1_GRID[i], f"first-stage t[{i}]")
    expected = BASELINE_2NS[power]
    for name, target in expected.items():
        _close(float(rows[-1][name]), target, f"reference 2ns {name}", 1e-7)
    return {"power_w": power, "rows": len(rows), "final_time_s": float(rows[-1]["time"]),
            "final": {key: float(rows[-1][key]) for key in expected}}


def checkpoint_manifest(directory: Path) -> dict[str, object]:
    if not directory.is_dir():
        raise ValueError(f"checkpoint directory absent: {directory}")
    files = sorted(x for x in directory.rglob("*") if x.is_file())
    if not files:
        raise ValueError("checkpoint directory empty")
    # Both mesh and state must be present. Checkpoint output is version-dependent.
    # Current MOOSE writes serialized restartable state with .rd; older
    # versions used .cpr/.cp. Never accept a mesh-only checkpoint.
    if not any(x.suffix in (".rd", ".cpr", ".cp") for x in files):
        raise ValueError("checkpoint restartable state (.rd/.cpr/.cp) absent")
    if not any("mesh" in x.name for x in files):
        raise ValueError("checkpoint mesh absent")
    return {"checkpoint_directory": str(directory),
            "files": [{"path": str(x.relative_to(directory)),
                       "bytes": x.stat().st_size,
                       "sha256": hashlib.sha256(x.read_bytes()).hexdigest()}
                      for x in files]}


def verify_restart(first_csv: Path, current_csv: Path, power: int, log: Path) -> dict[str, object]:
    first = verify_first(first_csv, power)
    if not log.is_file():
        raise ValueError("no MOOSE recovery log")
    log_text = log.read_text(encoding="utf-8", errors="replace")
    if not re.search(r"(?i)\brecover(?:y|ing|ed)?\b", log_text):
        raise ValueError("no MOOSE recovery evidence in actual solver stdout")
    rows = read_csv(current_csv)
    if not rows:
        raise ValueError("no CSV rows after recovery")
    times = [float(row["time"]) for row in rows]
    if any(not math.isfinite(t) for t in times):
        raise ValueError("nonfinite time after recovery")
    # Genuine continuation must solve beyond t=2ns; no re-initialized 0ns-only acceptance.
    if not any(t > END_2NS + 1e-15 for t in times):
        raise ValueError("MOOSE recovery did not solve after 2ns")
    _close(times[-1], END_4NS, "recovered final time", 1e-12)
    return {"power_w": power, "checkpoint_2ns": first,
            "recovered_last_time_s": times[-1], "recovered_csv_times_s": times,
            "recovery_in_log": True}


def self_test() -> None:
    source = ("[Executioner]\n  type = Transient\n  end_time = 2.0000000000000001e-09\n"
              "  [TimeStepper]\n    type = TimeSequenceStepper\n"
              "    time_sequence = '0 1.0000000000000001e-09 2.0000000000000001e-09'\n"
              "  []\n[]\n[Outputs]\n  csv = true\n  exodus = true\n[]\n")
    one = enable_checkpoint(source)
    verify_grid(one, 1)
    two = extend_checkpoint(one)
    verify_grid(two, 2)
    try:
        enable_checkpoint(one)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate checkpoint accepted")
    try:
        extend_checkpoint(source)
    except ValueError:
        pass
    else:
        raise AssertionError("missing checkpoint accepted")
    try:
        verify_grid(two.replace("3.0000000000000004e-09", "6e-9"), 2)
    except ValueError:
        pass
    else:
        # Some interpreters render 3ns as 3.0000000000000004e-09, others 3e-09
        if "3.0000000000000004e-09" in two:
            raise AssertionError("incorrect recovery sequence accepted")
    print("OXYGEN24_CHECKPOINT_RESTART_SELFTEST_PASS")


def main() -> None:
    p = argparse.ArgumentParser()
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--enable-checkpoint", type=Path)
    group.add_argument("--extend", type=Path)
    group.add_argument("--verify-checkpoint", type=Path)
    group.add_argument("--verify-first", type=Path)
    group.add_argument("--verify-restart", type=Path)
    group.add_argument("--self-test", action="store_true")
    p.add_argument("--power-w", type=int, choices=[400, 1000])
    p.add_argument("--first-csv", type=Path)
    p.add_argument("--log", type=Path)
    p.add_argument("--manifest", type=Path)
    args = p.parse_args()
    if args.self_test:
        self_test()
        return
    if args.enable_checkpoint is not None:
        args.enable_checkpoint.write_text(
            enable_checkpoint(args.enable_checkpoint.read_text(encoding="utf-8")), encoding="utf-8")
        print("OXYGEN24_2NS_CHECKPOINT_OUTPUT_ENABLED_PASS")
        return
    if args.extend is not None:
        args.extend.write_text(
            extend_checkpoint(args.extend.read_text(encoding="utf-8")), encoding="utf-8")
        print("OXYGEN24_2NS_TO_4NS_GRID_EXTENDED_PASS")
        return
    if args.verify_checkpoint is not None:
        result = checkpoint_manifest(args.verify_checkpoint)
        print("OXYGEN24_MOOSE_CHECKPOINT_FILES_PRESENT_PASS", len(result["files"]))
    elif args.verify_first is not None:
        if args.power_w is None:
            p.error("--power-w required")
        result = verify_first(args.verify_first, args.power_w)
        print("OXYGEN24_2NS_MATCHES_PINNED_REFERENCE_PASS", args.power_w)
    else:
        if args.power_w is None or args.first_csv is None or args.log is None:
            p.error("--power-w, --first-csv and --log required")
        result = verify_restart(args.first_csv, args.verify_restart, args.power_w, args.log)
        print("OXYGEN24_2NS_TO_4NS_ACTUAL_RECOVERY_PASS", args.power_w)
    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
