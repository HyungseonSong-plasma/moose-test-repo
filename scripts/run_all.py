#!/usr/bin/env python3

import subprocess
import sys
from pathlib import Path


def main():
    repo_root = Path(__file__).resolve().parents[1]
    manifests = sorted((repo_root / "tests").rglob("test.json"))
    if not manifests:
        print("No tests found.")
        return 0

    failures = []
    for manifest in manifests:
        case_dir = manifest.parent
        print("\n" + "=" * 80)
        print(case_dir.relative_to(repo_root))
        print("=" * 80)
        p = subprocess.run(
            [sys.executable, str(repo_root / "scripts" / "run_test.py"), str(case_dir)]
        )
        if p.returncode != 0:
            failures.append(str(case_dir.relative_to(repo_root)))

    print("\n" + "=" * 80)
    print(f"TOTAL: {len(manifests)}  PASS: {len(manifests)-len(failures)}  FAIL: {len(failures)}")
    if failures:
        print("Failed cases:")
        for case in failures:
            print(f"  - {case}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
