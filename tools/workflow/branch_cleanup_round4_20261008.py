#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PROV = ROOT / "docs" / "provenance" / "branch-cleanup-2026-10-08-round4"
WORKFLOW = ROOT / ".github" / "workflows" / "issue202-branch-cleanup-pr-history-once.yml"
SCRIPT = Path(__file__)

# branch -> (PR number, required disposition)
# required disposition: MERGED or CLOSED_UNMERGED
TARGETS = {
    "issue-scientific-centralization-compatibility": (352, "MERGED"),
    "physicsapp-qualified-migration-20260927": (338, "MERGED"),
    "matrix-physical-ei19": (341, "CLOSED_UNMERGED"),
    "matrix-physical-ei20": (342, "CLOSED_UNMERGED"),
    "matrix-physical-h05": (343, "CLOSED_UNMERGED"),
    "matrix-physical-edetach": (344, "CLOSED_UNMERGED"),
    "matrix-physical-energy-smokes": (345, "CLOSED_UNMERGED"),
    "matrix-physical-grounded-sheath": (346, "CLOSED_UNMERGED"),
    "experiment-wall-temperature-subgrid-pr": (362, "CLOSED_UNMERGED"),
}
OPERATIONAL_TARGET = "ops/branch-cleanup-round4-20261008"


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, check=check, capture_output=True)


def refs() -> dict[str, str]:
    cp = run(["git", "ls-remote", "--heads", "origin"])
    out: dict[str, str] = {}
    for line in cp.stdout.splitlines():
        if not line.strip():
            continue
        sha, ref = line.split("\t", 1)
        prefix = "refs/heads/"
        if ref.startswith(prefix):
            out[ref[len(prefix):]] = sha
    return dict(sorted(out.items()))


def open_pr_heads() -> set[str]:
    repo = os.environ.get("GITHUB_REPOSITORY", "HyungseonSong-plasma/moose-test-repo")
    cp = run(["gh", "api", "--paginate", f"repos/{repo}/pulls?state=open&per_page=100", "--jq", ".[].head.ref"])
    return {x.strip() for x in cp.stdout.splitlines() if x.strip()}


def pr_snapshot(number: int) -> tuple[str, bool, str]:
    repo = os.environ.get("GITHUB_REPOSITORY", "HyungseonSong-plasma/moose-test-repo")
    cp = run([
        "gh", "api", f"repos/{repo}/pulls/{number}",
        "--jq", "[.state, (.merged_at != null), .head.ref] | @tsv",
    ])
    state, merged, head = cp.stdout.strip().split("\t")
    return state, merged == "true", head


def write_rows(path: Path, rows: list[tuple[str, ...]]) -> None:
    path.write_text("".join("\t".join(row) + "\n" for row in rows), encoding="utf-8")


def valid_disposition(state: str, merged: bool, required: str) -> bool:
    if required == "MERGED":
        return state == "closed" and merged
    if required == "CLOSED_UNMERGED":
        return state == "closed" and not merged
    return False


def main() -> int:
    PROV.mkdir(parents=True, exist_ok=True)
    before = refs()
    write_rows(PROV / "refs-before.tsv", [(b, s) for b, s in before.items()])

    snapshots: list[tuple[str, ...]] = []
    candidates: list[tuple[str, str, str]] = []
    skipped: list[tuple[str, str, str]] = []
    open_heads = open_pr_heads()

    for branch, (pr, required) in TARGETS.items():
        sha = before.get(branch, "")
        state, merged, head = pr_snapshot(pr)
        snapshots.append((branch, str(pr), state, str(merged).lower(), head, required, sha or "ABSENT"))
        if not sha:
            skipped.append((branch, "", "ALREADY_ABSENT"))
            continue
        if branch in open_heads:
            skipped.append((branch, sha, "OPEN_PR_HEAD"))
            continue
        if head != branch:
            skipped.append((branch, sha, f"PR_HEAD_MISMATCH:{head}"))
            continue
        if not valid_disposition(state, merged, required):
            skipped.append((branch, sha, f"PR_DISPOSITION_MISMATCH:{state}:{merged}"))
            continue
        candidates.append((branch, sha, f"PR_{pr}_{required}"))

    # The staging branch is disposable only after its PR is no longer open.
    op_sha = before.get(OPERATIONAL_TARGET, "")
    if op_sha and OPERATIONAL_TARGET not in open_heads:
        candidates.append((OPERATIONAL_TARGET, op_sha, "OBSOLETE_OPERATIONAL_BRANCH"))
    elif op_sha:
        skipped.append((OPERATIONAL_TARGET, op_sha, "OPEN_PR_HEAD"))

    write_rows(PROV / "pr-snapshots.tsv", snapshots)
    write_rows(PROV / "candidates.tsv", candidates)
    write_rows(PROV / "skipped-predelete.tsv", skipped)

    fresh_refs = refs()
    fresh_open_heads = open_pr_heads()
    deleted: list[tuple[str, str, str]] = []
    mutation_skips: list[tuple[str, str, str]] = []
    failed: list[tuple[str, str, str]] = []

    for branch, expected_sha, reason in candidates:
        if branch in fresh_open_heads:
            mutation_skips.append((branch, expected_sha, "BECAME_OPEN_PR_HEAD"))
            continue
        current = fresh_refs.get(branch, "")
        if current != expected_sha:
            mutation_skips.append((branch, expected_sha, f"SHA_CHANGED:{current or 'ABSENT'}"))
            continue
        cp = run([
            "git", "push",
            f"--force-with-lease=refs/heads/{branch}:{expected_sha}",
            "origin", f":refs/heads/{branch}",
        ], check=False)
        if cp.returncode == 0:
            deleted.append((branch, expected_sha, reason))
        else:
            detail = (cp.stderr or cp.stdout).strip().replace("\n", " | ")
            failed.append((branch, expected_sha, detail or "DELETE_FAILED"))

    after = refs()
    write_rows(PROV / "refs-after.tsv", [(b, s) for b, s in after.items()])
    write_rows(PROV / "deleted.tsv", deleted)
    write_rows(PROV / "mutation-skips.tsv", mutation_skips)
    write_rows(PROV / "failed.tsv", failed)

    (PROV / "README.md").write_text(
        "# Branch cleanup provenance — round 4\n\n"
        "Date: 2026-10-08\n\n"
        "Deletion contract:\n"
        "- target only branches with explicit PR provenance;\n"
        "- require merged=true for accepted historical implementation branches;\n"
        "- require closed+unmerged for obsolete matrix/draft experiment branches;\n"
        "- require the PR head ref to exactly equal the target branch;\n"
        "- preserve every current open-PR head;\n"
        "- require exact live SHA equality and delete with force-with-lease;\n"
        "- retain unrelated experiments and named archives for later review.\n\n"
        f"Branches before: {len(before)}\n"
        f"PR-governed targets: {len(TARGETS)}\n"
        f"Candidates including operational branch: {len(candidates)}\n"
        f"Deleted: {len(deleted)}\n"
        f"Pre-delete skips: {len(skipped)}\n"
        f"Mutation skips: {len(mutation_skips)}\n"
        f"Failures: {len(failed)}\n"
        f"Branches after: {len(after)}\n",
        encoding="utf-8",
    )

    WORKFLOW.unlink(missing_ok=True)
    SCRIPT.unlink(missing_ok=True)
    run(["git", "config", "user.name", "samuel-branch-cleanup"])
    run(["git", "config", "user.email", "actions@users.noreply.github.com"])
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "Record 2026-10-08 round-4 branch cleanup"])
    cp = run(["git", "push", "origin", "HEAD:main"], check=False)
    if cp.returncode != 0:
        sys.stderr.write((cp.stdout or "") + (cp.stderr or ""))
        return 2
    if failed:
        print(f"BRANCH_CLEANUP_ROUND4=PARTIAL deleted={len(deleted)} failed={len(failed)}")
        return 1
    print(f"BRANCH_CLEANUP_ROUND4=PASS deleted={len(deleted)} remaining={len(after)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
