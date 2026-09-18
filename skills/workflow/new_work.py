#!/usr/bin/env python3
"""Allocate monotonic issue-local work identities and fail-closed manifest skeletons."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", required=True, type=int)
    parser.add_argument(
        "--kind", required=True, choices=["experiments", "refactor"]
    )
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--root",
        default=str(
            Path(__file__).resolve().parents[2] / "automation" / "manifests"
        ),
    )
    args = parser.parse_args()
    folder = Path(args.root) / (
        "experiments" if args.kind == "experiments" else "refactors"
    )
    folder.mkdir(parents=True, exist_ok=True)
    pattern = re.compile(
        rf"^Issue_{args.issue}_{re.escape(args.kind)}(\d+)\.json$"
    )
    used = [
        int(match.group(1))
        for path in folder.glob(f"Issue_{args.issue}_{args.kind}*.json")
        if (match := pattern.match(path.name))
    ]
    sequence = max(used, default=0) + 1
    identity = f"Issue_{args.issue}_{args.kind}{sequence:02d}"
    if args.kind == "experiments":
        stages = [{
            "id": "P0",
            "name": "configure P0",
            "command": [
                "python3", "-c",
                "raise SystemExit('TODO: configure P0')",
            ],
        }]
    else:
        stages = [{
            "id": "VALIDATE",
            "name": "configure refactor validation",
            "command": [
                "python3", "-c",
                "raise SystemExit('TODO: configure refactor')",
            ],
        }]
    payload = {
        "schema_version": 1,
        "issue": args.issue,
        "kind": args.kind,
        "sequence": sequence,
        "title": args.title,
        "stages": stages,
        "artifacts": [],
    }
    path = folder / f"{identity}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(path)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
