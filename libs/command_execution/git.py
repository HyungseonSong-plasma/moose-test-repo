"""Bounded-duration local Git subprocess primitive.

The caller owns authorization, argument selection and side effects. This
runner is not read-only: existing test replay also manages local worktrees.
It does not provide a remote repository mutation route.
"""
from __future__ import annotations

from pathlib import Path
import subprocess


def run_git(root: Path, *args: str) -> bytes:
    """Run caller-selected Git arguments without a shell; preserve raw bytes."""
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=30,
    )
    if result.returncode:
        raise ValueError("GIT_SOURCE_UNAVAILABLE: " +
                         result.stderr.decode("utf-8", "replace").strip()[:250])
    return result.stdout


__all__ = ["run_git"]
