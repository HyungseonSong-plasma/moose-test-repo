"""Reusable artifact ownership, freshness, and identity checks.

Functions in this module return mechanical facts only. Callers own any final
PASS/HOLD/FAIL or scientific evidence policy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence


def is_direct_child(path: Path, parent: Path) -> bool:
    """Return whether ``path`` resolves directly under ``parent``."""
    return Path(path).resolve().parent == Path(parent).resolve()


def paths_distinct(left: Path, right: Path) -> bool:
    """Return whether two paths resolve to different filesystem locations."""
    return Path(left).resolve() != Path(right).resolve()


def identity_stable(before: str, after: str) -> bool:
    """Return whether an externally computed identity digest stayed unchanged."""
    return bool(before) and before == after


def current_run_artifact(
    path: Path,
    *,
    expected_parent: Path,
    existed_before: bool,
    exists_after: bool,
) -> bool:
    """Check that an artifact is newly produced under its declared owner directory."""
    return (
        is_direct_child(path, expected_parent)
        and not existed_before
        and exists_after
    )


def snapshot_unchanged(before: Sequence[str], after: Sequence[str]) -> bool:
    """Return whether an ordered external snapshot is unchanged."""
    return tuple(before) == tuple(after)


def summarize_checks(checks: Mapping[str, bool]) -> dict[str, object]:
    """Summarize named boolean checks without assigning domain-specific policy."""
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
