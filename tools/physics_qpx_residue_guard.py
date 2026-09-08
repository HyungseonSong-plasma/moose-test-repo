#!/usr/bin/env python3
"""Fail if active public-CI surfaces retain legacy QPX naming/contracts."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    ROOT / ".github" / "workflows",
    ROOT / "ci" / "physics-build-base",
    ROOT / "ci" / "physics-runtime-image",
    ROOT / "physics_app" / "dependencies.lock",
)

FORBIDDEN = re.compile(r"qpx", re.IGNORECASE)
TEXT_SUFFIXES = {".yml", ".yaml", ".py", ".sh", ".txt", ".md", ".lock", ""}


def iter_files(path: Path):
    if path.is_file():
        yield path
        return
    if path.is_dir():
        for candidate in sorted(path.rglob("*")):
            if candidate.is_file() and candidate.suffix in TEXT_SUFFIXES:
                yield candidate


def main() -> int:
    findings: list[str] = []
    for target in TARGETS:
        for path in iter_files(target):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if FORBIDDEN.search(line):
                    rel = path.relative_to(ROOT)
                    findings.append(f"{rel}:{line_no}: {line.strip()}")

    if findings:
        print("ACTIVE_QPX_RESIDUE=FAIL")
        print("\n".join(findings))
        return 1

    print("ACTIVE_QPX_RESIDUE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
