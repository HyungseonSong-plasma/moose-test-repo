#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import os
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PROV = ROOT / "docs" / "provenance" / "branch-cleanup-2026-10-08-round3"
WORKFLOW = ROOT / ".github" / "workflows" / "issue202-branch-cleanup-closed-issues-once.yml"
SCRIPT = Path(__file__)

ISSUE_PREFIXES = {
    234: ("issue-234-",),
    295: ("issue-295-",),
    306: ("issue-306-",),
    310: ("issue-310-",),
    315: ("issue-315-",),
    332: ("issue-332-",),
    333: ("issue-333-",),
    334: ("issue-334-",),
    335: ("issue-335-",),
    336: ("issue-336-",),
}

ARCHIVE_PRESERVE = {
    "issue-306-sequence08-baseline",
    "qualified/issue310-gummel-optimized",
}

OPERATIONAL_TARGETS = {
    "ops-trigger-branch-cleanup-20261008",
    "ops/branch-cleanup-round3-20261008",
}


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, check=check, capture_output=True)


def remote_refs() -> dict[str, str]:
    result = run(["git", "ls-remote", "--heads", "origin"])
    refs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        sha, ref = line.split("\t", 1)
        prefix = "refs/heads/"
        if ref.startswith(prefix):
            refs[ref[len(prefix):]] = sha
    return dict(sorted(refs.items()))


def open_pr_heads() -> set[str]:
    repo = os.environ.get("GITHUB_REPOSITORY", "HyungseonSong-plasma/moose-test-repo")
    result = run([
        "gh", "api", "--paginate",
        f"repos/{repo}/pulls?state=open&per_page=100",
        "--jq", ".[].head.ref",
    ])
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def issue_state(number: int) -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "HyungseonSong-plasma/moose-test-repo")
    result = run(["gh", "api", f"repos/{repo}/issues/{number}", "--jq", ".state"])
    return result.stdout.strip()


def write_refs(path: Path, refs: dict[str, str]) -> None:
    path.write_text("".join(f"{branch}\t{sha}\n" for branch, sha in refs.items()), encoding="utf-8")


def write_rows(path: Path, rows: list[tuple[str, ...]]) -> None:
    path.write_text("".join("\t".join(row) + "\n" for row in rows), encoding="utf-8")


def owning_issue(branch: str) -> int | None:
    for number, prefixes in ISSUE_PREFIXES.items():
        if any(branch.startswith(prefix) for prefix in prefixes):
            return number
    return None


def main() -> int:
    PROV.mkdir(parents=True, exist_ok=True)

    before = remote_refs()
    write_refs(PROV / "refs-before.tsv", before)

    issue_states = {number: issue_state(number) for number in ISSUE_PREFIXES}
    (PROV / "issue-states.tsv").write_text(
        "".join(f"{number}\t{state}\n" for number, state in sorted(issue_states.items())),
        encoding="utf-8",
    )

    open_heads = open_pr_heads()
    (PROV / "open-pr-heads.txt").write_text(
        "".join(f"{name}\n" for name in sorted(open_heads)), encoding="utf-8"
    )

    candidates: list[tuple[str, str, str]] = []
    preserved: list[tuple[str, str, str]] = []
    skipped: list[tuple[str, str, str]] = []

    for branch, sha in before.items():
        if branch in ARCHIVE_PRESERVE:
            preserved.append((branch, sha, "ARCHIVE_PRESERVE"))
            continue
        if branch in open_heads:
            preserved.append((branch, sha, "OPEN_PR_HEAD"))
            continue
        if branch in OPERATIONAL_TARGETS:
            candidates.append((branch, sha, "OBSOLETE_OPERATIONAL_BRANCH"))
            continue

        issue = owning_issue(branch)
        if issue is None:
            continue
        state = issue_states[issue]
        if state == "closed":
            candidates.append((branch, sha, f"CLOSED_ISSUE_{issue}"))
        else:
            skipped.append((branch, sha, f"ISSUE_{issue}_STATE_{state}"))

    write_rows(PROV / "preserved.tsv", preserved)
    write_rows(PROV / "candidates.tsv", candidates)
    write_rows(PROV / "skipped-predelete.tsv", skipped)

    # Fresh mutable evidence immediately before mutation.
    fresh_refs = remote_refs()
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

        result = run([
            "git", "push",
            f"--force-with-lease=refs/heads/{branch}:{expected_sha}",
            "origin", f":refs/heads/{branch}",
        ], check=False)
        if result.returncode == 0:
            deleted.append((branch, expected_sha, reason))
        else:
            detail = (result.stderr or result.stdout).strip().replace("\n", " | ")
            failed.append((branch, expected_sha, detail or "DELETE_FAILED"))

    after = remote_refs()
    write_refs(PROV / "refs-after.tsv", after)
    write_rows(PROV / "deleted.tsv", deleted)
    write_rows(PROV / "mutation-skips.tsv", mutation_skips)
    write_rows(PROV / "failed.tsv", failed)

    remaining_candidates = [branch for branch, _, _ in candidates if branch in after]
    (PROV / "README.md").write_text(
        "# Branch cleanup provenance — round 3\n\n"
        "Date: 2026-10-08\n\n"
        "Deletion contract:\n"
        "- target only explicit closed-issue branch families plus obsolete cleanup-operation branches;\n"
        "- refresh every owning issue state from GitHub and require `closed`;\n"
        "- preserve all current open-PR heads;\n"
        "- preserve `issue-306-sequence08-baseline` and `qualified/issue310-gummel-optimized` as historical numerical archives;\n"
        "- require exact live SHA equality immediately before mutation;\n"
        "- perform deletion with exact-SHA `--force-with-lease`;\n"
        "- leave unrelated experiment/matrix/prototype branches for a later review.\n\n"
        f"Branches before: {len(before)}\n"
        f"Candidates: {len(candidates)}\n"
        f"Deleted: {len(deleted)}\n"
        f"Preserved by archive/open-PR gate: {len(preserved)}\n"
        f"Mutation skips: {len(mutation_skips)}\n"
        f"Failures: {len(failed)}\n"
        f"Branches after: {len(after)}\n"
        f"Qualified candidates still present: {len(remaining_candidates)}\n",
        encoding="utf-8",
    )

    WORKFLOW.unlink(missing_ok=True)
    SCRIPT.unlink(missing_ok=True)

    run(["git", "config", "user.name", "samuel-branch-cleanup"])
    run(["git", "config", "user.email", "actions@users.noreply.github.com"])
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "Record 2026-10-08 round-3 branch cleanup"])
    push = run(["git", "push", "origin", "HEAD:main"], check=False)
    if push.returncode != 0:
        sys.stderr.write((push.stdout or "") + (push.stderr or ""))
        return 2

    if failed:
        print(f"BRANCH_CLEANUP_ROUND3=PARTIAL deleted={len(deleted)} failed={len(failed)}")
        return 1

    print(
        "BRANCH_CLEANUP_ROUND3=PASS "
        f"deleted={len(deleted)} mutation_skips={len(mutation_skips)} remaining={len(after)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
