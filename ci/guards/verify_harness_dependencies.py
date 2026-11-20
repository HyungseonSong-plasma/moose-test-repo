#!/usr/bin/env python3
"""Repository CI entrypoint for Harness-owned dependency verification."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from physics_harness.code.diagnostics import GitSourceProvider, ScanRequest
from physics_harness.code.diagnostics.request import ScanBudget
from physics_harness.code.verification import (
    DependencyContract, verify_dependency_repository,
)


def main() -> int:
    try:
        repo = json.loads(
            (ROOT / ".chatgpt-operation.json").read_text(encoding="utf-8")
        )["repository"]
        config = json.loads(
            (ROOT / "ci/contracts/harness_dependencies.json").read_text(
                encoding="utf-8"
            )
        )
        contract = DependencyContract.from_mapping(config)
        revision = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
        request = ScanRequest(
            repository=repo,
            revision=revision,
            includes=(contract.package_root + "/*.py",),
            collectors=("python_ast",),
            budget=ScanBudget(max_files=10000, max_bytes=100_000_000,
                              max_seconds=180),
        )
        result = verify_dependency_repository(
            request, GitSourceProvider(ROOT), contract
        )
    except (OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"HARNESS_DEPENDENCY_VERIFICATION: UNVERIFIED ({exc})")
        return 1

    for item in result.findings:
        print(f"{item.category}: {item.path}:{item.line}@{item.blob_sha}: "
              f"{item.source} -> {item.target}: {item.reason}")
    print(f"HARNESS_DEPENDENCY_FILES={result.checked_files}")
    print(f"HARNESS_DEPENDENCY_VERIFICATION: {result.status}")
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
