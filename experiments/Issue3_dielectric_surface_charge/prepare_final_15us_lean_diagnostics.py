#!/usr/bin/env python3
"""Create a lean diagnostic derivative of the accepted #331 15 us input.

The accepted baseline is never modified in place.  Final Issue #3 production
inputs keep only baseline safety/conservation sentinels plus diagnostics named
`issue3_*`.  Full-field Exodus output is restricted to five checkpoints.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

BASELINE_KEEP = {
    "ne_min",
    "ni_min",       # O2+
    "nm_min",       # O-
    "nop_min",      # O+
    "mean_energy_min",
    "potential_min",
    "potential_max",
    "charge_integral",
    "neutral_sum_w_min",
    "neutral_sum_w_max",
    "neutral_rho_min",
    "neutral_mass_total",
    "neutral_outlet_mass",
    "stageb4_ion_total_neutral_return_rate",
}

CHECKPOINTS = "0 1e-6 5e-6 1e-5 1.5e-5"


def find_section(text: str, header: str, next_header: str | None = None):
    start = text.find(header)
    if start < 0:
        raise ValueError(f"missing section {header}")
    if next_header:
        end = text.find(next_header, start + len(header))
        if end < 0:
            raise ValueError(f"missing section after {header}: {next_header}")
    else:
        end = len(text)
    return start, end, text[start:end]


def split_leaf_blocks(section: str):
    lines = section.splitlines(keepends=True)
    if not lines or lines[0].strip() != "[Postprocessors]":
        raise ValueError("expected [Postprocessors] section")

    blocks = []
    prefix = lines[0]
    suffix = ""
    i = 1
    while i < len(lines):
        if lines[i].strip() == "[]":
            suffix = "".join(lines[i:])
            break
        match = re.match(r"^\s{2}\[([^\]]+)\]\s*$", lines[i].rstrip("\n"))
        if not match:
            prefix += lines[i]
            i += 1
            continue
        name = match.group(1)
        begin = i
        i += 1
        while i < len(lines) and lines[i].strip() != "[]":
            i += 1
        if i >= len(lines):
            raise ValueError(f"unterminated postprocessor block {name}")
        i += 1
        blocks.append((name, "".join(lines[begin:i])))
    return prefix, blocks, suffix


def set_initial_final(block: str) -> str:
    replacement = "    execute_on = 'INITIAL FINAL'"
    if re.search(r"^\s+execute_on\s*=.*$", block, flags=re.MULTILINE):
        return re.sub(
            r"^\s+execute_on\s*=.*$", replacement, block, flags=re.MULTILINE
        )
    pos = block.rfind("  []")
    if pos < 0:
        raise ValueError("malformed postprocessor block")
    return block[:pos] + replacement + "\n" + block[pos:]


def prune_postprocessors(section: str):
    prefix, blocks, suffix = split_leaf_blocks(section)
    kept = []
    removed = []
    output = [prefix]
    for name, block in blocks:
        if name in BASELINE_KEEP:
            output.append(set_initial_final(block))
            kept.append(name)
        elif name.startswith("issue3_"):
            # Issue #3 diagnostics own their cadence.  A cumulative current/time
            # integral may legitimately need TIMESTEP_END even when output is sparse.
            output.append(block)
            kept.append(name)
        else:
            removed.append(name)
    output.append(suffix or "[]\n")
    return "".join(output), kept, removed


def lean_outputs() -> str:
    return f"""[Outputs]\n  # Scalar acceptance evidence only at start/end.\n  [acceptance_csv]\n    type = CSV\n    file_base = issue3_final_15us_acceptance\n    execute_on = 'INITIAL FINAL'\n  []\n\n  # Spatial evidence at five checkpoints instead of every timestep.\n  [checkpoint_exodus]\n    type = Exodus\n    file_base = issue3_final_15us_checkpoints\n    execute_on = 'INITIAL TIMESTEP_END'\n    sync_times = '{CHECKPOINTS}'\n    sync_only = true\n  []\n[]\n"""


def transform(text: str):
    pp_start, pp_end, pp = find_section(text, "[Postprocessors]", "[Executioner]")
    new_pp, kept, removed = prune_postprocessors(pp)
    text = text[:pp_start] + new_pp + text[pp_end:]

    out_start = text.find("[Outputs]")
    if out_start < 0:
        raise ValueError("missing [Outputs] section")
    text = text[:out_start] + lean_outputs()
    return text, kept, removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()

    if args.source.resolve() == args.target.resolve():
        raise SystemExit("refusing in-place rewrite: preserve the accepted baseline")

    text, kept, removed = transform(args.source.read_text(encoding="utf-8"))
    args.target.write_text(text, encoding="utf-8")

    print(f"source={args.source}")
    print(f"target={args.target}")
    print(f"kept_postprocessors={len(kept)}")
    print(f"removed_postprocessors={len(removed)}")
    print("kept=" + ",".join(kept))
    print("removed=" + ",".join(removed))
    print("exodus_checkpoints_s=" + CHECKPOINTS.replace(" ", ","))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
