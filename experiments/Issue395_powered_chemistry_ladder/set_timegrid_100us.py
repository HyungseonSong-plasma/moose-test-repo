#!/usr/bin/env python3
"""Set the Issue #395 transient time grid to end at 100 us.

Staging:
  0--0.1 us   : 1 ns x 100
  0.1--1 us   : 10 ns x 90
  1--10 us    : 100 ns x 90
  10--100 us  : 1000 ns x 90
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

EXEC_RE = re.compile(r"(?ms)^\[Executioner\]\n(?P<body>.*?)^\[\]\n")
END_RE = re.compile(r"(?m)^(?P<indent>\s*)end_time\s*=\s*\S+\s*$")
SEQ_RE = re.compile(r"(?m)^(?P<indent>\s*)time_sequence\s*=\s*'[^']*'\s*$")


def format_seconds(ns: int) -> str:
    if ns == 0:
        return "0"
    return f"{ns * 1.0e-9:.17g}"


def build_times_ns() -> list[int]:
    times = list(range(0, 101, 1))
    times.extend(range(110, 1001, 10))
    times.extend(range(1100, 10001, 100))
    times.extend(range(11000, 100001, 1000))

    if times[0] != 0 or times[-1] != 100000:
        raise RuntimeError("time grid endpoints are incorrect")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise RuntimeError("time grid is not strictly increasing")
    if len(times) - 1 != 370:
        raise RuntimeError(f"unexpected step count: {len(times)-1}, expected 370")
    return times


def transform(text: str) -> tuple[str, int]:
    matches = list(EXEC_RE.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"expected one [Executioner] block, found {len(matches)}")

    match = matches[0]
    body = match.group("body")
    times_ns = build_times_ns()
    sequence = " ".join(format_seconds(ns) for ns in times_ns)

    body, n_end = END_RE.subn(lambda m: f"{m.group('indent')}end_time = 1e-4", body, count=1)
    if n_end != 1:
        raise RuntimeError(f"expected one end_time in Executioner, found {n_end}")

    body, n_seq = SEQ_RE.subn(
        lambda m: f"{m.group('indent')}time_sequence = '{sequence}'", body, count=1
    )
    if n_seq != 1:
        raise RuntimeError(f"expected one time_sequence in Executioner, found {n_seq}")

    out = text[: match.start("body")] + body + text[match.end("body") :]
    return out, len(times_ns) - 1


def verify(text: str, expected_steps: int) -> None:
    match = EXEC_RE.search(text)
    if match is None:
        raise RuntimeError("missing [Executioner] after transformation")
    body = match.group("body")

    if re.search(r"(?m)^\s*end_time\s*=\s*1e-4\s*$", body) is None:
        raise RuntimeError("end_time is not 100 us")

    seq_match = re.search(r"(?m)^\s*time_sequence\s*=\s*'([^']*)'\s*$", body)
    if seq_match is None:
        raise RuntimeError("missing time_sequence after transformation")
    vals = [float(x) for x in seq_match.group(1).split()]

    if len(vals) - 1 != expected_steps:
        raise RuntimeError("serialized time_sequence has wrong step count")
    if abs(vals[-1] - 1.0e-4) > 1.0e-16:
        raise RuntimeError(f"serialized final time is {vals[-1]}, expected 1e-4")

    def nearest_index(value: float) -> int:
        return min(range(len(vals)), key=lambda i: abs(vals[i] - value))

    checks = [
        (5.0e-8, 1.0e-9, "0--0.1 us: 1 ns"),
        (5.0e-7, 1.0e-8, "0.1--1 us: 10 ns"),
        (5.0e-6, 1.0e-7, "1--10 us: 100 ns"),
        (5.0e-5, 1.0e-6, "10--100 us: 1000 ns"),
    ]
    for probe, want, label in checks:
        i = nearest_index(probe)
        got = vals[i + 1] - vals[i]
        if abs(got - want) > 1.0e-16:
            raise RuntimeError(f"{label} spacing mismatch: got {got}, expected {want}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} INPUT")
    path = Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")
    transformed, steps = transform(text)
    verify(transformed, steps)
    path.write_text(transformed, encoding="utf-8")

    print("ISSUE395_TIMEGRID_100US_PASS")
    print("end_time_us=100")
    print("segment_0_to_0p1us_dt_ns=1 steps=100")
    print("segment_0p1_to_1us_dt_ns=10 steps=90")
    print("segment_1_to_10us_dt_ns=100 steps=90")
    print("segment_10_to_100us_dt_ns=1000 steps=90")
    print(f"total_steps={steps}")


if __name__ == "__main__":
    main()
