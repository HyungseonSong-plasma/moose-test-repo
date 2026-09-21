#!/usr/bin/env python3
"""Consumer-side E2E proof for Paul skill activation telemetry.

This intentionally lives outside normal initialization and imports the exact pinned
central telemetry primitive only when explicitly executed for Issue #23 validation.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

CENTRAL_REVISION = "268c0960253efaea3a99c9952fe9bf98885c57c4"
CONSUMER = "HyungseonSong-plasma/moose-test-repo"


def load_telemetry(central_root: Path):
    path = central_root / "src/chatgpt_operation/telemetry.py"
    spec = importlib.util.spec_from_file_location("issue23_telemetry", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load telemetry primitive from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def event(observed_at: str) -> dict:
    return {
        "event": "skill_activation",
        "activation_id": "moose-test-repo-issue23-e2e-state-refresh",
        "skill": "state-refresh",
        "skill_path": "skills/state-refresh/README.md",
        "consumer": CONSUMER,
        "central_revision": CENTRAL_REVISION,
        "trigger": "ISSUE23_E2E",
        "observed_at": observed_at,
        "source": "github_execution",
        "outcome": "invoked",
    }


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: issue23_telemetry_e2e.py <exact-central-root>")
    central_root = Path(sys.argv[1]).resolve()
    actual = __import__("subprocess").check_output(
        ["git", "-C", str(central_root), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != CENTRAL_REVISION:
        raise SystemExit(f"central revision mismatch: {actual}")

    telemetry = load_telemetry(central_root)
    first = event("2026-09-21T10:00:00Z")
    retry = event("2026-09-21T10:05:00Z")
    result = telemetry.aggregate([first, retry], known_skills=["state-refresh", "repository-mutation"])

    expected = {
        "event_count": 1,
        "duplicate_count": 1,
        "activations_by_skill_day": {"state-refresh|2026-09-21": 1},
        "activations_by_skill_consumer": {f"state-refresh|{CONSUMER}": 1},
        "activations_by_trigger": {"ISSUE23_E2E": 1},
        "skills_with_zero_observed_activation": ["repository-mutation"],
    }
    for key, expected_value in expected.items():
        if result[key] != expected_value:
            raise RuntimeError(
                f"unexpected {key}: expected {expected_value!r}, got {result[key]!r}"
            )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
