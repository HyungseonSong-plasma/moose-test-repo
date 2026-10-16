#!/usr/bin/env python3
"""Set the Issue #395 transient time grid to end at 15 us.

Startup staging is preserved:
  0--0.1 us : 1 ns
  0.1--1 us : 10 ns

The 1--15 us segment is parameterized by --dt-ns.  Intended discriminator
values are 50 ns and 25 ns.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


EXEC_RE = re.compile(r"(?ms)^\[Executioner\]\n(?P<body>.*?)^\[\]\n")
END_RE = re.compile(r"(?m)^(?P<indent>\s*)end_time\s*=\s*\S+\s*$")
SEQ_RE = re.compile(r"(?m)^(?P<indent>\s*)time_sequence\s*=\s*'[^']*'\s*$")


def format_seconds(ns: int) -> str:
    if ns == 0:
        return "0"
    return f"{ns * 1.0e-9:.17g}"


def build_times_ns(dt_ns: int) -> list[int]:
    if dt_ns <= 0:
        raise ValueError("dt_ns must be positive")
    if 14000 % dt_ns != 0:
        raise ValueError("dt_ns must exactly divide the 1--15 us interval (14000 ns)")

    times = list(range(0, 101, 1))
    times.extend(range(110, 1001, 10))
    times.extend(range(1000 + dt_ns, 15001, dt_ns))

    if times[0] != 0 or times[-1] != 15000:
        raise RuntimeError("time grid endpoints are incorrect")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise RuntimeError("time grid is not strictly increasing")

    expected_steps = 100 + 90 + 14000 // dt_ns
    if len(times) - 1 != expected_steps:
        raise RuntimeError(
            f"unexpected step count: got {len(times)-1}, expected {expected_steps}"
        )
    return times


def transform(text: str, dt_ns: int) -> tuple[str, int]:
    matches = list(EXEC_RE.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"expected one [Executioner] block, found {len(matches)}")

    match = matches[0]
    body = match.group("body")
    times_ns = build_times_ns(dt_ns)
    sequence = " ".join(format_seconds(ns) for ns in times_ns)

    body, n_end = END_RE.subn(lambda m: f"{m.group('indent')}end_time = 1.5e-5", body, count=1)
    if n_end != 1:
        raise RuntimeError(f"expected one end_time in Executioner, found {n_end}")

    body, n_seq = SEQ_RE.subn(
        lambda m: f"{m.group('indent')}time_sequence = '{sequence}'", body, count=1
    )
    if n_seq != 1:
        raise RuntimeError(f"expected one time_sequence in Executioner, found {n_seq}")

    out = text[: match.start("body")] + body + text[match.end("body") :]
    return out, len(times_ns) - 1


def verify(text: str, dt_ns: int, expected_steps: int) -> None:
    match = EXEC_RE.search(text)
    if match is None:
        raise RuntimeError("missing [Executioner] after transformation")
    body = match.group("body")

    if re.search(r"(?m)^\s*end_time\s*=\s*1\.5e-5\s*$", body) is None:
        raise RuntimeError("end_time is not 15 us")

    seq_match = re.search(r"(?m)^\s*time_sequence\s*=\s*'([^']*)'\s*$", body)
    if seq_match is None:
        raise RuntimeError("missing time_sequence after transformation")
    vals = [float(x) for x in seq_match.group(1).split()]

    if len(vals) - 1 != expected_steps:
        raise RuntimeError("serialized time_sequence has wrong step count")
    if abs(vals[-1] - 1.5e-5) > 1.0e-16:
        raise RuntimeError(f"serialized final time is {vals[-1]}, expected 1.5e-5")

    def nearest_index(value: float) -> int:
        return min(range(len(vals)), key=lambda i: abs(vals[i] - value))

    i_50ns = nearest_index(5.0e-8)
    i_500ns = nearest_index(5.0e-7)
    i_5us = nearest_index(5.0e-6)
    checks = [
        (vals[i_50ns + 1] - vals[i_50ns], 1.0e-9, "startup 1 ns"),
        (vals[i_500ns + 1] - vals[i_500ns], 1.0e-8, "startup 10 ns"),
        (vals[i_5us + 1] - vals[i_5us], dt_ns * 1.0e-9, f"main {dt_ns} ns"),
    ]
    for got, want, label in checks:
        if abs(got - want) > 1.0e-16:
            raise RuntimeError(f"{label} spacing mismatch: got {got}, expected {want}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--dt-ns", type=int, required=True, choices=(25, 50))
    args = parser.parse_args()

    text = args.input.read_text(encoding="utf-8")
    transformed, steps = transform(text, args.dt_ns)
    verify(transformed, args.dt_ns, steps)
    args.input.write_text(transformed, encoding="utf-8")

    print("ISSUE395_TIMEGRID_15US_PASS")
    print("end_time_us=15")
    print("startup_0_to_0p1us_dt_ns=1")
    print("startup_0p1_to_1us_dt_ns=10")
    print(f"main_1_to_15us_dt_ns={args.dt_ns}")
    print(f"total_steps={steps}")


if __name__ == "__main__":
    main()
