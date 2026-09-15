#!/usr/bin/env python3
"""CI entrypoint for Issue-236 M1-A with governed W5 runtime-asset staging.

Kept separate from the scientific split builder so this correction is visibly a
harness/staging fix: it copies the same rate/chemistry assets used by the W5
production path before validating references and invoking MOOSE.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from experiments.Issue236_m1a_multiapp_smoke import run as base


def _stage(out: Path, *, dt_e: float) -> tuple[Path, dict[str, Any]]:
    parent, child, meta = base.build_split(dt_e=dt_e)
    case_dir = out / "case"
    staged = base.stage_case(
        base.SOURCE,
        case_dir,
        input_text=parent,
        input_name="input.i",
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=(
            "input_out*",
            "electron_sub*",
            "*.log",
            "*.e",
            "*.exo",
            "prepare_evidence.json",
        ),
    )
    (case_dir / "electron_sub.i").write_text(child, encoding="utf-8")

    # Exact staging contract already used by Issue-216 W5 and its R2 successors.
    base.w5.s5r._copy_runtime_assets(case_dir)

    meta["staging"] = staged
    meta["parent_references"] = base.validate_referenced_files(
        parent, case_dir, skip_dynamic=True
    )
    meta["child_references"] = base.validate_referenced_files(
        child, case_dir, skip_dynamic=True
    )
    (case_dir / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return case_dir, meta


base._stage = _stage

if __name__ == "__main__":
    raise SystemExit(base.main())
