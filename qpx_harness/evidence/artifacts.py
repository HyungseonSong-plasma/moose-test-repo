"""Reusable artifact ownership, freshness, and identity checks.

Functions in this module return mechanical facts only. Callers own any final
PASS/HOLD/FAIL or scientific evidence policy.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence


def is_direct_child(path: Path, parent: Path) -> bool:
    return Path(path).resolve().parent == Path(parent).resolve()


def paths_distinct(left: Path, right: Path) -> bool:
    return Path(left).resolve() != Path(right).resolve()


def identity_stable(before: str, after: str) -> bool:
    return before == after


def current_run_artifact(
    path: Path,
    *,
    expected_parent: Path,
    existed_before: bool,
    exists_after: bool,
) -> bool:
    return (
        is_direct_child(path, expected_parent)
        and not existed_before
        and exists_after
    )


def snapshot_unchanged(before: Sequence[str], after: Sequence[str]) -> bool:
    return tuple(before) == tuple(after)


def write_json_bundle(
    root: Path,
    payloads: Mapping[str, tuple[str, object]],
) -> dict[str, str]:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    paths: dict[str, str] = {}
    filenames: set[str] = set()
    for raw_label in sorted(payloads):
        label = str(raw_label)
        filename, payload = payloads[raw_label]
        filename = str(filename)
        filename_path = Path(filename)
        if not label:
            raise ValueError("artifact label must be non-empty")
        if (
            not filename
            or filename in {".", ".."}
            or filename_path.name != filename
        ):
            raise ValueError(
                f"artifact filename must be a direct-child name: {filename!r}"
            )
        if filename in filenames:
            raise ValueError(f"duplicate artifact filename: {filename!r}")
        filenames.add(filename)

        path = root / filename
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        paths[label] = str(path)
    return paths


def summarize_checks(checks: Mapping[str, bool]) -> dict[str, object]:
    normalized = {str(name): bool(ok) for name, ok in checks.items()}
    blockers = [name for name, ok in normalized.items() if not ok]
    return {
        "ok": not blockers,
        "checks": [
            {"id": name, "ok": ok}
            for name, ok in normalized.items()
        ],
        "blockers": blockers,
    }
