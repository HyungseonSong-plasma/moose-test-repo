#!/usr/bin/env python3
"""Opt-in bounded Oxygen24 real-physics smoke: two 1 ns steps, not physics acceptance."""
from __future__ import annotations
import argparse
import re
from pathlib import Path

STEPS = 2
DT = 1e-9
END_TIME = STEPS * DT
EXEC = re.compile(r"(?ms)^\[Executioner\]\n(?P<body>.*?)^\[\]\s*$")
END = re.compile(r"(?m)^(?P<prefix>\s*end_time\s*=\s*)[^#\n]+$")
GRID = re.compile(r"(?m)^(?P<prefix>\s*time_sequence\s*=\s*)'[^']*'\s*$")


def _executioner(text):
    found = list(EXEC.finditer(text))
    if len(found) != 1:
        raise ValueError(f"required one Executioner, found {len(found)}")
    return found[0]


def verify(text):
    body = _executioner(text).group("body")
    ends = list(END.finditer(body))
    grids = list(GRID.finditer(body))
    if len(ends) != 1 or len(grids) != 1:
        raise ValueError("missing/ambiguous Executioner time grid")
    end = float(ends[0].group(0).split("=", 1)[1].strip())
    values = [float(x) for x in grids[0].group(0).split("'", 2)[1].split()]
    expected = [0.0, 1e-9, 2e-9]
    if abs(end - END_TIME) > 1e-18 or len(values) != len(expected) or any(
        abs(a-b) > 1e-18 for a, b in zip(values, expected)
    ):
        raise ValueError(f"smoke time grid mismatch: end={end} sequence={values}")
    return {"steps": STEPS, "end_time_ns": 2.0, "time_s": values}


def transform(text):
    match = _executioner(text)
    body = match.group("body")
    if len(list(END.finditer(body))) != 1 or len(list(GRID.finditer(body))) != 1:
        raise ValueError("expected exactly one end_time and time_sequence")
    body = END.sub(lambda m: m.group("prefix") + f"{END_TIME:.17g}", body)
    sequence = " ".join(["0"] + [f"{i*DT:.17g}" for i in range(1, STEPS+1)])
    body = GRID.sub(lambda m: m.group("prefix") + f"'{sequence}'", body)
    result = text[:match.start("body")] + body + text[match.end("body"):]
    verify(result)
    return result


def self_test():
    source = (
        "[Executioner]\n  type = Transient\n  end_time = 1e-4\n"
        "  [TimeStepper]\n    time_sequence = '0 1e-9 2e-9 3e-9'\n  []\n[]\n"
    )
    modified = transform(source)
    assert transform(modified) == modified
    for invalid in (
        source,
        modified.replace(f"end_time = {END_TIME:.17g}", "end_time = 1e-4"),
        modified.replace("time_sequence = ", "bad_sequence = "),
    ):
        try:
            verify(invalid)
        except ValueError:
            continue
        raise AssertionError("negative P0 time-grid mutation accepted")
    print("OXYGEN24_SMOKE_2NS_P0_SELFTEST_PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.input is None:
        parser.error("input required")
    if not args.verify:
        args.input.write_text(transform(args.input.read_text(encoding="utf-8")), encoding="utf-8")
    print("OXYGEN24_SMOKE_2NS_TIMEGRID_PASS",
          verify(args.input.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
