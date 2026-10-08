#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

TARGETS = [
    ("ci-main-hybrid-regression", "234b0fd4bbeeab7667f3fdfe7e044b61ac7335f3"),
    ("promote-hybrid-baseline", "3b556a61de80c5c50448e78f5364eaea393b6693"),
    ("promote-hybrid-baseline-clean", "78311b96d82e32cfd53ce46bfd877f16ceaeb01c"),
    ("issue-357-icp-profile-transplant", "fcce510ef08535c3265111b1b07ffec0a48c8202"),
    ("issue-359-qualified-gummel-icp", "0352a39966abf49b4762ce638e6dba45e0caa225"),
    ("issue-gummel-api-cleanup", "05fd063f98406892553e9f4929245097084c9289"),
    ("gummel-heavy-sibling-parity", "c4dfbf44718d1f9b71965166ccae6293c2b2d3a0"),
    ("qualification-physical-coupled-equivalence", "0d6b5df981699f8b2dbdd9517d1f51b9253ef4e9"),
    ("physical-electron-state-normalization-removal", "f799c8fdcdac8d90f32bb10b41c2d80d00e481b8"),
    ("issue-310-secant-history-seed-seq08", "0dda68e704b6989132cd0b1fed10828bbd51b033"),
    ("issue-309-standard-moose-sheath-refactor", "b1d581c56642f26ba7fed45a7be30395d57125d2"),
    ("issue-253-g1-gummel-dt-release", "34d6e7c2edb533c0e3a474bb411bfeab8a92c085"),
]

ROOT = Path(__file__).resolve().parents[2]
PROV = ROOT / "docs" / "provenance" / "branch-cleanup-2026-10-08"
WORKFLOW = ROOT / ".github" / "workflows" / "branch-cleanup-20261008-once.yml"
SCRIPT = Path(__file__)


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
    path.write_text("".join(f"{name}\t{sha}\n" for name, sha in values.items()), encoding="utf-8")


def main() -> int:
    PROV.mkdir(parents=True, exist_ok=True)
    before = refs()
    write_refs(PROV / "refs-before.tsv", before)

    deleted = []
    failed = []
    for branch, expected in TARGETS:
        current = refs().get(branch, "")
        if current != expected:
            failed.append((branch, expected, current, "SHA_MISMATCH"))
            continue
        result = run(["git", "push", "origin", "--delete", branch], check=False)
        if result.returncode == 0:
            deleted.append((branch, expected))
        else:
            failed.append((branch, expected, current, "DELETE_FAILED"))

    after = refs()
    write_refs(PROV / "refs-after.tsv", after)
    (PROV / "deleted.tsv").write_text(
        "".join(f"{b}\t{s}\n" for b, s in deleted), encoding="utf-8"
    )
    (PROV / "failed.tsv").write_text(
        "".join(f"{b}\t{e}\t{c}\t{r}\n" for b, e, c, r in failed), encoding="utf-8"
    )
    (PROV / "README.md").write_text(
        "# Branch cleanup provenance\n\n"
        "Date: 2026-10-08\n\n"
        "Policy:\n"
        "- keep `main`;\n"
        "- keep `experiment-full-fem-contour-mesh` as the pre-Maxwell transport archive;\n"
        "- keep branches tied to current open issues and active operational work;\n"
        "- delete only the first reviewed batch of merged, closed, superseded, or retired branches;\n"
        "- delete only when the live remote SHA exactly matches the pre-cleanup inventory.\n\n"
        f"Requested targets: {len(TARGETS)}\n"
        f"Deleted: {len(deleted)}\n"
        f"Failed: {len(failed)}\n",
        encoding="utf-8",
    )

    WORKFLOW.unlink(missing_ok=True)
    SCRIPT.unlink(missing_ok=True)

    run(["git", "config", "user.name", "physics-branch-cleanup"])
    run(["git", "config", "user.email", "actions@users.noreply.github.com"])
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "Record 2026-10-08 branch cleanup provenance"])
    push = run(["git", "push", "origin", "HEAD:main"], check=False)
    if push.returncode != 0:
        sys.stderr.write(push.stdout + push.stderr)
        return 2

    if failed or len(deleted) != len(TARGETS):
        print("BRANCH_CLEANUP=FAIL", file=sys.stderr)
        print(f"deleted={len(deleted)} failed={len(failed)}", file=sys.stderr)
        return 1

    print(f"BRANCH_CLEANUP=PASS deleted={len(deleted)} remaining={len(after)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
