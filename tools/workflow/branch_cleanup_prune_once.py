#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

TARGETS = {
    "issue-234-m0-multirate-preflight": "83d58acc1a719a443e6ed51ae0690cc90c0c37bf",
    "issue-234-m1-1d-heavy-surface-e0": "3026015ca57937a1461a267d9053ac72ab1a199f",
    "issue-234-m1-1d-poisson-stage1": "09592568a50b68172e74696ed5b1d1f8a83cfbc4",
    "issue-234-m1-1d-thermal-loss-e0": "6a54b5737e21ba364933903292734617694b2ef7",
    "issue-234-m1-chemistry-off-10cycle": "52435945db07a93556e17232debd0fe871d1dcd2",
    "issue-234-m1-chemistry-off-joule-10cycle": "b0ed22721bbb6a1c0c09eacdb3c3d49c80019829",
    "issue-234-m1-integrated-boundary-2e8": "f7322553bbe2598dd4750b48e1d10c1bb9d0ce88",
    "issue-234-m1-multiapp-density-scan": "b536a9acec99e467b26a267f989ddac127494d94",
    "issue-234-m1-multiapp-electron-poisson": "18246fca630924ff82defc4d28786f20de504928",
    "issue-234-m1-representation-gate": "24f492664909ce6dc626418a28dc2b5d2ce0e582",
    "issue-234-m1-sheath-ab-science": "1047b8639a976030ae97622cfaf4492fbe43f67a",
}

KEEPS = {
    "issue-234-m1-1d-electron-drift-surface": "5d073a116f24c1446554b6cee6c7de380a670164",
    "issue-234-m1-1d-poisson-observer": "0f29d576052ee24da06f47a884eb193bf68b1ba8",
    "issue-234-m1-1d-poisson-scaling-ab": "6091828e13278b9675fe101a76077f5aab5daec8",
    "issue-234-m1-fixed-chi-scan": "cf4d8ec4bbd2fc483a3c60d4b90cfaecaa29e311",
    "issue-234-m1-fixed-density-dt-scan": "f80a4c8c4a1d60a48c071508044dd66677c01170",
    "issue-234-m1-density-robustness-ne1e15": "5ddb47e0a3bf0b22e50b78c31490361cd749309b",
}

ROOT = Path(__file__).resolve().parents[2]
PROV = ROOT / "docs" / "provenance" / "branch-cleanup-2026-09-18-active-prune"

def run(args, *, check=True):
    return subprocess.run(args, cwd=ROOT, text=True, check=check, capture_output=True)

def refs():
    result = run(["git", "ls-remote", "--heads", "origin"])
    out = {}
    for line in result.stdout.splitlines():
        sha, ref = line.split("\t", 1)
        if ref.startswith("refs/heads/"):
            out[ref[len("refs/heads/"):]] = sha
    return dict(sorted(out.items()))

def write_refs(path: Path, values: dict[str, str]) -> None:
    path.write_text("".join(f"{name}\t{sha}\n" for name, sha in sorted(values.items())), encoding="utf-8")

def main() -> int:
    PROV.mkdir(parents=True, exist_ok=True)
    before = refs()
    write_refs(PROV / "refs-before.tsv", before)
    write_refs(PROV / "planned-delete.tsv", TARGETS)
    write_refs(PROV / "planned-keep.tsv", KEEPS)

    expected_names = {"main", *TARGETS, *KEEPS}
    problems = []
    if set(before) != expected_names:
        problems.append("unexpected ref set: " + repr(sorted(set(before) ^ expected_names)))
    for branch, expected in {**TARGETS, **KEEPS}.items():
        current = before.get(branch)
        if current != expected:
            problems.append(f"{branch}: expected {expected}, got {current}")

    if problems:
        (PROV / "preflight-failures.txt").write_text("\n".join(problems) + "\n", encoding="utf-8")
        print("BRANCH_PRUNE=PREFLIGHT_FAIL", file=sys.stderr)
        for problem in problems:
            print(problem, file=sys.stderr)
        return 2

    deleted = {}
    failures = {}
    for branch, expected in TARGETS.items():
        result = run(["git", "push", "origin", "--delete", branch], check=False)
        if result.returncode == 0:
            deleted[branch] = expected
        else:
            failures[branch] = (expected, result.stdout + result.stderr)

    after = refs()
    write_refs(PROV / "refs-after.tsv", after)
    write_refs(PROV / "deleted.tsv", deleted)
    (PROV / "failed.tsv").write_text(
        "".join(
            f"{branch}\t{expected}\t{message.strip()}\n"
            for branch, (expected, message) in sorted(failures.items())
        ),
        encoding="utf-8",
    )

    expected_after = {"main", *KEEPS}
    unexpected_after = {name: sha for name, sha in after.items() if name not in expected_after}
    write_refs(PROV / "unexpected-after.tsv", unexpected_after)

    keep_mismatch = {
        name: (expected, after.get(name))
        for name, expected in KEEPS.items()
        if after.get(name) != expected
    }
    (PROV / "keep-mismatch.tsv").write_text(
        "".join(
            f"{name}\t{expected}\t{actual or ''}\n"
            for name, (expected, actual) in sorted(keep_mismatch.items())
        ),
        encoding="utf-8",
    )

    (PROV / "README.md").write_text(
        "# Issue 234 branch-prune provenance\n\n"
        "Date: 2026-09-18\n\n"
        "Purpose: remove completed/superseded Issue #234 experiment branches while retaining only the branches still needed as direct or upstream provenance for active #253/#254 work.\n\n"
        "Retention policy:\n"
        "- keep main;\n"
        "- keep the accepted 1D electron drift/surface control used by #253;\n"
        "- keep the Poisson observer and scaling A/B branches that motivate #253 G1-A;\n"
        "- keep the two accepted dielectric-relaxation baseline/replication branches used by #253 G1-D;\n"
        "- keep the fixed-chi branch that reproduces #254's validator defect;\n"
        "- delete completed, superseded, or no-longer-active #234 experiment branches;\n"
        "- delete only when the live remote SHA exactly matches the pre-prune inventory.\n\n"
        "The exact pre/post refs and deletion results are preserved in this directory.\n",
        encoding="utf-8",
    )

    canonical_guard = run(["git", "show", "HEAD^:tools/workflow/workflow_guard.py"]).stdout
    (ROOT / "tools" / "workflow" / "workflow_guard.py").write_text(canonical_guard, encoding="utf-8")
    (ROOT / ".github" / "workflows" / "branch-cleanup-prune-once.yml").unlink(missing_ok=True)
    Path(__file__).unlink(missing_ok=True)

    run(["git", "config", "user.name", "physics-branch-cleanup"])
    run(["git", "config", "user.email", "actions@users.noreply.github.com"])
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "Prune completed Issue 234 branches"])
    push = run(["git", "push", "origin", "HEAD:main"], check=False)
    if push.returncode != 0:
        sys.stderr.write(push.stdout + push.stderr)
        return 3

    if failures or unexpected_after or keep_mismatch or len(deleted) != len(TARGETS) or set(after) != expected_after:
        print("BRANCH_PRUNE=FAIL", file=sys.stderr)
        print(
            f"deleted={len(deleted)} failures={len(failures)} remaining={len(after)} "
            f"unexpected={len(unexpected_after)} keep_mismatch={len(keep_mismatch)}",
            file=sys.stderr,
        )
        return 1

    print(f"BRANCH_PRUNE=PASS deleted={len(deleted)} remaining={len(after)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
