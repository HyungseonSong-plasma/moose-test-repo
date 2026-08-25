#!/usr/bin/env python3

import json
import subprocess
import sys
from pathlib import Path


def parse_requested_type(argv):
    if len(argv) == 1:
        return "canonical"

    if len(argv) == 3 and argv[1] == "--type" and argv[2] in {"canonical", "diagnostic", "all"}:
        return argv[2]

    raise SystemExit(
        "usage: python3 scripts/run_all.py [--type canonical|diagnostic|all]"
    )


def manifest_type(manifest: Path) -> str:
    cfg = json.loads(manifest.read_text())
    test_type = cfg.get("type", "canonical")
    if test_type not in {"canonical", "diagnostic"}:
        raise SystemExit(f"invalid test type '{test_type}' in {manifest}")
    return test_type


def main():
    requested_type = parse_requested_type(sys.argv)
    repo_root = Path(__file__).resolve().parents[1]
    manifests = sorted((repo_root / "tests").rglob("test.json"))

    selected = []
    for manifest in manifests:
        test_type = manifest_type(manifest)
        if requested_type == "all" or test_type == requested_type:
            selected.append((manifest, test_type))

    if not selected:
        print(f"No {requested_type} tests found.")
        return 0

    failures = []
    for manifest, test_type in selected:
        case_dir = manifest.parent
        print("\n" + "=" * 80)
        print(case_dir.relative_to(repo_root), f"[{test_type}]")
        print("=" * 80)
        p = subprocess.run(
            [sys.executable, str(repo_root / "scripts" / "run_test.py"), str(case_dir)]
        )
        if p.returncode != 0:
            failures.append(str(case_dir.relative_to(repo_root)))

    print("\n" + "=" * 80)
    print(
        f"TYPE: {requested_type}  TOTAL: {len(selected)}  "
        f"PASS: {len(selected)-len(failures)}  FAIL: {len(failures)}"
    )
    if failures:
        print("Failed cases:")
        for case in failures:
            print(f"  - {case}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
