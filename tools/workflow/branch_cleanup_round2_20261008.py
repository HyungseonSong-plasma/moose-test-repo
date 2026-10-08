#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PROV = ROOT / "docs" / "provenance" / "branch-cleanup-2026-10-08-round2"
WORKFLOW = ROOT / ".github" / "workflows" / "issue202-branch-cleanup-once.yml"
SCRIPT = Path(__file__)

PRESERVE = {
    "main",
    "experiment-full-fem-contour-mesh",
    "issue-280-sol-gateway-cutover",
    "issue331-stageb-monolithic-charged",
    "issue-331-governed-compile-manifest",
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


def write_refs(path: Path, refs: dict[str, str]) -> None:
    path.write_text("".join(f"{branch}\t{sha}\n" for branch, sha in refs.items()), encoding="utf-8")


def write_rows(path: Path, rows: list[tuple[str, ...]]) -> None:
    path.write_text("".join("\t".join(row) + "\n" for row in rows), encoding="utf-8")


def is_ancestor(sha: str, main_sha: str) -> bool:
    result = run(["git", "merge-base", "--is-ancestor", sha, main_sha], check=False)
    return result.returncode == 0


def main() -> int:
    PROV.mkdir(parents=True, exist_ok=True)

    # Fetch every branch tip so ancestry tests are against real remote objects.
    run([
        "git", "fetch", "--no-tags", "--prune", "origin",
        "+refs/heads/*:refs/remotes/origin/*",
    ])

    before = remote_refs()
    write_refs(PROV / "refs-before.tsv", before)
    if "main" not in before:
        raise RuntimeError("remote main not found")
    main_sha = before["main"]

    open_heads_initial = open_pr_heads()
    (PROV / "open-pr-heads-before.txt").write_text(
        "".join(f"{name}\n" for name in sorted(open_heads_initial)), encoding="utf-8"
    )

    preserved: list[tuple[str, str, str]] = []
    candidates: list[tuple[str, str, str]] = []
    skipped: list[tuple[str, str, str]] = []

    for branch, sha in before.items():
        if branch in PRESERVE:
            preserved.append((branch, sha, "EXPLICIT_PRESERVE"))
            continue
        if branch in open_heads_initial:
            preserved.append((branch, sha, "OPEN_PR_HEAD"))
            continue
        if is_ancestor(sha, main_sha):
            candidates.append((branch, sha, "ANCESTOR_OF_MAIN"))
        else:
            skipped.append((branch, sha, "HAS_UNMERGED_OR_NONANCESTRY_HISTORY"))

    write_rows(PROV / "preserved.tsv", preserved)
    write_rows(PROV / "candidates.tsv", candidates)
    write_rows(PROV / "skipped-predelete.tsv", skipped)

    # Refresh mutable PR state immediately before mutation.
    open_heads_fresh = open_pr_heads()
    (PROV / "open-pr-heads-predelete.txt").write_text(
        "".join(f"{name}\n" for name in sorted(open_heads_fresh)), encoding="utf-8"
    )

    deleted: list[tuple[str, str]] = []
    failed: list[tuple[str, str, str]] = []
    mutation_skips: list[tuple[str, str, str]] = []

    for branch, expected_sha, _ in candidates:
        if branch in open_heads_fresh:
            mutation_skips.append((branch, expected_sha, "BECAME_OPEN_PR_HEAD"))
            continue

        current = remote_refs().get(branch, "")
        if current != expected_sha:
            mutation_skips.append((branch, expected_sha, f"SHA_CHANGED:{current or 'ABSENT'}"))
            continue

        # Force-with-lease makes the deletion itself conditional on the exact
        # inventory SHA, closing the read/delete race rather than merely checking
        # the SHA immediately before an unconditional delete.
        result = run([
            "git", "push",
            f"--force-with-lease=refs/heads/{branch}:{expected_sha}",
            "origin", f":refs/heads/{branch}",
        ], check=False)
        if result.returncode == 0:
            deleted.append((branch, expected_sha))
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
        "# Branch cleanup provenance — round 2\n\n"
        "Date: 2026-10-08\n\n"
        "Deletion contract:\n"
        "- preserve `main`;\n"
        "- preserve the pre-Maxwell transport archive and active architecture branches;\n"
        "- preserve every current open-PR head;\n"
        "- delete only branches whose recorded tip is an ancestor of the current `main`;\n"
        "- require exact live SHA equality immediately before mutation;\n"
        "- perform deletion with `--force-with-lease=<ref>:<expected_sha>`;\n"
        "- leave squash/non-ancestor or unique-history branches for later manual review.\n\n"
        f"Main SHA: `{main_sha}`\n\n"
        f"Branches before: {len(before)}\n"
        f"Explicit/open-PR preserved: {len(preserved)}\n"
        f"Ancestry-qualified candidates: {len(candidates)}\n"
        f"Deleted: {len(deleted)}\n"
        f"Mutation skips: {len(mutation_skips)}\n"
        f"Failures: {len(failed)}\n"
        f"Branches after: {len(after)}\n"
        f"Qualified candidates still present: {len(remaining_candidates)}\n",
        encoding="utf-8",
    )

    # Self-remove the one-shot execution surface; retain provenance only.
    WORKFLOW.unlink(missing_ok=True)
    SCRIPT.unlink(missing_ok=True)

    run(["git", "config", "user.name", "samuel-branch-cleanup"])
    run(["git", "config", "user.email", "actions@users.noreply.github.com"])
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "Record 2026-10-08 round-2 branch cleanup"])
    push = run(["git", "push", "origin", "HEAD:main"], check=False)
    if push.returncode != 0:
        sys.stderr.write((push.stdout or "") + (push.stderr or ""))
        return 2

    if failed:
        print(f"BRANCH_CLEANUP_ROUND2=PARTIAL deleted={len(deleted)} failed={len(failed)}")
        return 1

    print(
        "BRANCH_CLEANUP_ROUND2=PASS "
        f"deleted={len(deleted)} mutation_skips={len(mutation_skips)} "
        f"remaining={len(after)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
