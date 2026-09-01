"""Compatibility facade for generic evidence artifact mechanics."""

from .evidence.artifacts import (
    current_run_artifact,
    identity_stable,
    is_direct_child,
    paths_distinct,
    snapshot_unchanged,
    summarize_checks,
    write_json_bundle,
)

__all__ = [
    "current_run_artifact",
    "identity_stable",
    "is_direct_child",
    "paths_distinct",
    "snapshot_unchanged",
    "summarize_checks",
    "write_json_bundle",
]
