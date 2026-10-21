#!/usr/bin/env python3
"""Consumer-side regression for mandatory Samuel capability restoration.

This guards canonical bootstrap wording; it does not execute a ChatGPT init session.
Provider order/decision mechanics remain owned by the pinned central Samuel skills.
"""
from __future__ import annotations
import argparse
from pathlib import Path

REQUIRED = {
    "BOOTSTRAP.md": [
        "skills/catalog.json", "skills/capability-registry.json",
        "GITHUB_CAPABILITY_ROUTING=READY|BLOCKED",
        "GITHUB_MUTATION_PREFLIGHT=TRIGGER_REQUIRED",
        "GITHUB_BRANCH_DELETE", "GITHUB_MUTATION_CAPABILITY_VERDICT",
        "assert_capability_exhausted", "samuel-branch-delete.yml",
        "Initialization itself remains read-only",
        "even after a context reset",
        "If a connector lacks a particular operation",
    ],
    "WORKSPACE.md": [
        "moose-test-init", "GITHUB_CAPABILITY_ROUTING=READY",
        "GitHub state-changing operation", "BOOTSTRAP.md",
    ],
    "PROTOCOL_INDEX.md": [
        "GITHUB_BRANCH_DELETE", "GITHUB_MUTATION_CAPABILITY_VERDICT",
        "GITHUB_WORKFLOW_DISPATCH", "GITHUB_CAPABILITY_ROUTING=READY",
        "assert_capability_exhausted", "ROUTE-09",
    ],
    "docs/operating_system/README.md": [
        "skills/catalog.json", "skills/capability-registry.json",
        "GITHUB_CAPABILITY_ROUTING=READY|BLOCKED",
        "GITHUB_MUTATION_PREFLIGHT=TRIGGER_REQUIRED",
        "GITHUB_BRANCH_DELETE", "GITHUB_MUTATION_CAPABILITY_VERDICT",
    ],
}

def errors(texts: dict[str, str | None]) -> list[str]:
    found=[]
    for path,phrases in REQUIRED.items():
        content=texts.get(path)
        if content is None:
            found.append(f"{path}: absent")
            continue
        for phrase in phrases:
            if phrase not in content:
                found.append(f"{path}: missing '{phrase}'")
    return found

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--check",action="store_true")
    p.add_argument("--self-test",action="store_true")
    opts=p.parse_args()
    inputs={name:(opts.root/name).read_text(encoding="utf8") if (opts.root/name).is_file() else None for name in REQUIRED}
    issues=errors(inputs)
    if issues:
        print("\n".join("MOOSE_TEST_INIT_CAPABILITY_ROUTING_FAIL "+issue for issue in issues))
        return 1
    if opts.self_test:
        for name in REQUIRED:
            neg=dict(inputs)
            neg[name]=neg[name].replace(REQUIRED[name][0],"MISSING_MARKER")
            assert errors(neg),f"mutation for {name} was not detected"
        print("MOOSE_TEST_INIT_CAPABILITY_ROUTING_SELFTEST_PASS")
    if opts.check:
        print("MOOSE_TEST_INIT_CAPABILITY_ROUTING_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
