#!/usr/bin/env python3
"""Issue #395 exact 100-us grid for 200/300/400 W refined-mesh EI17 scan.

0–0.1 us:    1 ns x 100
0.1–2 us:   10 ns x 190
2–10 us:   100 ns x 80
10–100 us:  1 us  x 90
Total 460 steps and 461 time points.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re


SEGMENTS_NS = ((0, 100, 1, 100),
               (100, 2000, 10, 190),
               (2000, 10000, 100, 80),
               (10000, 100000, 1000, 90))
EXEC_RE = re.compile(r"(?ms)^\[Executioner\]\n(?P<body>.*?)^\[\]\n")


def build_grid_ns() -> list[int]:
    times = [0]
    for start, end, dt, steps in SEGMENTS_NS:
        if times[-1] != start or (end - start) != dt * steps:
            raise RuntimeError("inconsistent time segment")
        times.extend(range(start+dt, end+1, dt))
    if len(times) != 461 or times[-1] != 100000:
        raise RuntimeError("incorrect time grid: expected 461 points to 100us")
    return times


def transform(text: str) -> str:
    matches = list(EXEC_RE.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"expected one Executioner; found {len(matches)}")
    match = matches[0]
    seq = " ".join("0" if ns == 0 else f"{ns * 1e-9:.17g}" for ns in build_grid_ns())
    body = match.group("body")
    body, n1 = re.subn(r"(?m)^(\s*)end_time\s*=\s*\S+\s*$",r"\g<1>end_time = 1e-4",body,count=1)
    body, n2 = re.subn(r"(?m)^(\s*)time_sequence\s*=\s*'[^']*'\s*$",
                       lambda m:f"{m.group(1)}time_sequence = '{seq}'",body,count=1)
    if (n1,n2) != (1,1):
        raise RuntimeError(f"Executioner end_time/time_sequence missing: {(n1,n2)}")
    output=text[:match.start("body")]+body+text[match.end("body"):]
    check=EXEC_RE.search(output)
    if check is None:raise RuntimeError("Executioner lost on rewrite")
    tm=re.search(r"(?m)^\s*time_sequence = '([^']+)'$",check.group("body"))
    if tm is None:raise RuntimeError("time grid serialization failure")
    vals=[float(s) for s in tm.group(1).split()]
    expected=build_grid_ns()
    if len(vals)!=len(expected) or any(abs(t - ns*1e-9)>1e-15 for t,ns in zip(vals,expected)):
        raise RuntimeError("serialized time grid failed exact tolerance audit")
    return output


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("input",type=Path)
    args=p.parse_args()
    data=args.input.read_text(encoding="utf-8")
    args.input.write_text(transform(data),encoding="utf-8")
    print("ISSUE395_TIMEGRID_100US_460STEPS_PASS")
    print("power_W_matrix=200,300,400")
    print("end_time_us=100")
    for a,b,dt,n in SEGMENTS_NS:
        print(f"segment_{a}_to_{b}_ns_dt={dt}ns_steps={n}")
    print("total_steps=460")


if __name__=="__main__":
    main()
