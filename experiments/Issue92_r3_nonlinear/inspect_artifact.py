#!/usr/bin/env python3
"""Inspect an existing Issue #92 diagnostic artifact without running qpx-opt.

This tool is intentionally qpx-free. It is used when the one-shot diagnostic
lands on B7 because the runtime output contract was not parsed completely. It
reports exactly which residual markers are present and attempts a conservative
fallback parse of the existing D1 log.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

FLOAT = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
GLOBAL = re.compile(rf"(?m)^\s*(\d+)\s+Nonlinear\s+\|R\|\s*=\s*({FLOAT})")
SNES = re.compile(rf"(?m)^\s*(\d+)\s+SNES\s+Function\s+norm\s+({FLOAT})", re.I)
VAR = re.compile(rf"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*({FLOAT})\s*$")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
NONFINITE = re.compile(r"(?i)(?:^|[\s=(:,])(?:nan|[+-]?inf(?:inity)?)(?:$|[\s,;)])")

KNOWN_VARS = {
    "u", "v", "p",
    "w_O2s", "w_O2p", "w_O", "w_Om", "w_Op", "w_Os",
    "n_e",
}
GROUPS = {
    "FLOW": {"u", "v", "p"},
    "HEAVY_NEUTRAL": {"w_O2s", "w_O", "w_Os"},
    "HEAVY_CHARGED": {"w_O2p", "w_Om", "w_Op"},
    "ELECTRON": {"n_e"},
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _is_var_header(line: str) -> bool:
    lower = ANSI.sub("", line).strip().lower()
    return "residual" in lower and "individual" in lower and "variable" in lower


def fallback_parse(log: str) -> dict[str, Any]:
    clean = ANSI.sub("", log)
    globals_: list[float] = [float(m.group(2)) for m in GLOBAL.finditer(clean)]
    if not globals_:
        globals_ = [float(m.group(2)) for m in SNES.finditer(clean)]

    tables: list[dict[str, float]] = []
    current: dict[str, float] | None = None
    headers: list[str] = []
    for raw in clean.splitlines():
        if _is_var_header(raw):
            if current:
                tables.append(current)
            current = {}
            headers.append(raw.strip())
            continue
        if current is None:
            continue
        match = VAR.match(raw)
        if match:
            name, value_raw = match.groups()
            if name in KNOWN_VARS:
                value = float(value_raw)
                if math.isfinite(value):
                    current[name] = value
            continue
        if current and raw.strip():
            tables.append(current)
            current = None
    if current:
        tables.append(current)

    groups: list[dict[str, float]] = []
    dominant: list[str | None] = []
    ratios: list[float | None] = []
    for table in tables:
        row: dict[str, float] = {}
        for group, names in GROUPS.items():
            vals = [table[name] for name in names if name in table]
            if vals:
                row[group] = math.sqrt(sum(v * v for v in vals))
        groups.append(row)
        ordered = sorted(((value, group) for group, value in row.items()), reverse=True)
        if not ordered:
            dominant.append(None)
            ratios.append(None)
        elif len(ordered) == 1:
            dominant.append(ordered[0][1])
            ratios.append(math.inf if ordered[0][0] > 0 else 1.0)
        else:
            dominant.append(ordered[0][1])
            ratios.append(math.inf if ordered[1][0] == 0 and ordered[0][0] > 0 else ordered[0][0] / ordered[1][0] if ordered[1][0] else 1.0)

    return {
        "global_residual_count": len(globals_),
        "global_residuals": globals_,
        "variable_table_count": len(tables),
        "variable_tables": tables,
        "group_norms": groups,
        "dominant_groups": dominant,
        "dominance_ratios": ratios,
        "detected_variable_headers": headers,
        "nonfinite": bool(NONFINITE.search(clean)),
    }


def inspect(root: Path) -> dict[str, Any]:
    root = root.resolve()
    summary = _read_json(root / "summary.json")
    manifest = _read_json(root / "manifest.json")
    log_path = root / "logs" / "d1_residual_anatomy.log"
    if not log_path.is_file():
        candidates = sorted((root / "logs").glob("*d1*.log")) if (root / "logs").is_dir() else []
        if candidates:
            log_path = candidates[0]
    if not log_path.is_file():
        raise FileNotFoundError(f"D1 runtime log not found under {root / 'logs'}")

    raw = log_path.read_text(errors="replace")
    parsed = fallback_parse(raw)
    prior_d1 = summary.get("d1") if isinstance(summary, dict) else None
    result = {
        "artifact_root": str(root),
        "d1_log": str(log_path),
        "d1_log_bytes": len(raw.encode()),
        "runtime_returncode": None,
        "runtime_timed_out": None,
        "prior_selected_branch": summary.get("selected_branch") if isinstance(summary, dict) else None,
        "prior_terminal_reason": summary.get("terminal_reason") if isinstance(summary, dict) else None,
        "prior_parser": {
            "global_residual_count": len((prior_d1 or {}).get("global_residuals", [])) if isinstance(prior_d1, dict) else None,
            "variable_table_count": len((prior_d1 or {}).get("variable_norms", [])) if isinstance(prior_d1, dict) else None,
            "parse_complete": (prior_d1 or {}).get("parse_complete") if isinstance(prior_d1, dict) else None,
        },
        "fallback": parsed,
    }

    if isinstance(manifest, dict):
        for subrun in manifest.get("subruns", []):
            if isinstance(subrun, dict) and subrun.get("name") == "D1":
                run = subrun.get("run") or {}
                result["runtime_returncode"] = run.get("returncode")
                result["runtime_timed_out"] = run.get("timed_out")
                break

    if parsed["global_residual_count"] == 0:
        diagnosis = "GLOBAL_RESIDUAL_MARKER_MISSING"
    elif parsed["variable_table_count"] == 0:
        diagnosis = "VARIABLE_RESIDUAL_TABLE_MISSING_OR_UNRECOGNIZED"
    elif parsed["nonfinite"]:
        diagnosis = "NONFINITE_PRESENT"
    else:
        diagnosis = "FALLBACK_PARSE_COMPLETE"
    result["diagnosis"] = diagnosis
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_root", type=Path)
    args = parser.parse_args()
    try:
        result = inspect(args.artifact_root)
    except (FileNotFoundError, OSError) as exc:
        print(f"ISSUE92_ARTIFACT_INSPECT_ERROR: {exc}")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"ISSUE92_ARTIFACT_DIAGNOSIS: {result['diagnosis']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
