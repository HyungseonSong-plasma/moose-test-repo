#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PROV = ROOT / "docs" / "provenance" / "branch-cleanup-2026-10-08-round5"
WORKFLOW = ROOT / ".github" / "workflows" / "issue202-branch-cleanup-archive-ancestry-once.yml"
SCRIPT = Path(__file__)
ARCHIVE = "experiment-full-fem-contour-mesh"
OPERATIONAL = "ops/branch-cleanup-round5-20261008"
PRESERVE = {
    "main",
    ARCHIVE,
    "issue-280-sol-gateway-cutover",
    "issue331-stageb-monolithic-charged",
    "issue-331-governed-compile-manifest",
    "issue-306-sequence08-baseline",
    "qualified/issue310-gummel-optimized",
}


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, check=check, capture_output=True)


def refs() -> dict[str, str]:
    cp = run(["git", "ls-remote", "--heads", "origin"])
    out = {}
    for line in cp.stdout.splitlines():
        if not line.strip():
            continue
        sha, ref = line.split("\t", 1)
        if ref.startswith("refs/heads/"):
            out[ref.removeprefix("refs/heads/")] = sha
    return dict(sorted(out.items()))


def open_pr_heads() -> set[str]:
    repo = os.environ.get("GITHUB_REPOSITORY", "HyungseonSong-plasma/moose-test-repo")
    cp = run(["gh", "api", "--paginate", f"repos/{repo}/pulls?state=open&per_page=100", "--jq", ".[].head.ref"])
    return {x.strip() for x in cp.stdout.splitlines() if x.strip()}


def write_rows(path: Path, rows: list[tuple[str, ...]]) -> None:
    path.write_text("".join("\t".join(row) + "\n" for row in rows), encoding="utf-8")


def ancestor(child_sha: str, parent_sha: str) -> bool:
    return run(["git", "merge-base", "--is-ancestor", child_sha, parent_sha], check=False).returncode == 0


def main() -> int:
    PROV.mkdir(parents=True, exist_ok=True)
    run(["git", "fetch", "--no-tags", "--prune", "origin", "+refs/heads/*:refs/remotes/origin/*"])
    before = refs()
    write_rows(PROV / "refs-before.tsv", [(b, s) for b, s in before.items()])
    archive_sha = before.get(ARCHIVE)
    if not archive_sha:
        raise RuntimeError(f"archive branch missing: {ARCHIVE}")

    open_heads = open_pr_heads()
    candidates: list[tuple[str, str, str]] = []
    preserved: list[tuple[str, str, str]] = []
    nonancestors: list[tuple[str, str, str]] = []

    for branch, sha in before.items():
        if branch in PRESERVE:
            preserved.append((branch, sha, "EXPLICIT_PRESERVE"))
            continue
        if branch in open_heads:
            preserved.append((branch, sha, "OPEN_PR_HEAD"))
            continue
        if branch == OPERATIONAL:
            candidates.append((branch, sha, "OBSOLETE_OPERATIONAL_BRANCH"))
            continue
        if ancestor(sha, archive_sha):
            candidates.append((branch, sha, f"ANCESTOR_OF_{ARCHIVE}"))
        else:
            nonancestors.append((branch, sha, "NOT_CONTAINED_BY_ARCHIVE"))

    write_rows(PROV / "preserved.tsv", preserved)
    write_rows(PROV / "candidates.tsv", candidates)
    write_rows(PROV / "nonancestors.tsv", nonancestors)

    fresh = refs()
    fresh_open = open_pr_heads()
    deleted: list[tuple[str, str, str]] = []
    skips: list[tuple[str, str, str]] = []
    failed: list[tuple[str, str, str]] = []

    for branch, expected, reason in candidates:
        if branch in fresh_open:
            skips.append((branch, expected, "BECAME_OPEN_PR_HEAD"))
            continue
        current = fresh.get(branch, "")
        if current != expected:
            skips.append((branch, expected, f"SHA_CHANGED:{current or 'ABSENT'}"))
            continue
        cp = run([
            "git", "push",
            f"--force-with-lease=refs/heads/{branch}:{expected}",
            "origin", f":refs/heads/{branch}",
        ], check=False)
        if cp.returncode == 0:
            deleted.append((branch, expected, reason))
        else:
            detail = (cp.stderr or cp.stdout).strip().replace("\n", " | ")
            failed.append((branch, expected, detail or "DELETE_FAILED"))

    after = refs()
    write_rows(PROV / "refs-after.tsv", [(b, s) for b, s in after.items()])
    write_rows(PROV / "deleted.tsv", deleted)
    write_rows(PROV / "mutation-skips.tsv", skips)
    write_rows(PROV / "failed.tsv", failed)
    (PROV / "README.md").write_text(
        "# Branch cleanup provenance — round 5\n\n"
        "Date: 2026-10-08\n\n"
        f"Archive owner: `{ARCHIVE}` at `{archive_sha}`.\n\n"
        "Deletion contract:\n"
        "- preserve active/open-PR and explicitly named archive/architecture branches;\n"
        f"- delete a remaining branch only when its exact tip is a Git ancestor of `{ARCHIVE}`;\n"
        "- therefore the retained archive contains the deleted branch history;\n"
        "- require fresh exact SHA and force-with-lease for deletion;\n"
        "- leave branches not contained by the archive for separate semantic review.\n\n"
        f"Branches before: {len(before)}\n"
        f"Archive-contained candidates including operational branch: {len(candidates)}\n"
        f"Deleted: {len(deleted)}\n"
        f"Preserved: {len(preserved)}\n"
        f"Not contained by archive: {len(nonancestors)}\n"
        f"Mutation skips: {len(skips)}\n"
        f"Failures: {len(failed)}\n"
        f"Branches after: {len(after)}\n",
        encoding="utf-8",
    )

    WORKFLOW.unlink(missing_ok=True)
    SCRIPT.unlink(missing_ok=True)
    run(["git", "config", "user.name", "samuel-branch-cleanup"])
    run(["git", "config", "user.email", "actions@users.noreply.github.com"])
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "Record 2026-10-08 round-5 branch cleanup"])
    cp = run(["git", "push", "origin", "HEAD:main"], check=False)
    if cp.returncode != 0:
        sys.stderr.write((cp.stdout or "") + (cp.stderr or ""))
        return 2
    if failed:
        print(f"BRANCH_CLEANUP_ROUND5=PARTIAL deleted={len(deleted)} failed={len(failed)}")
        return 1
    print(f"BRANCH_CLEANUP_ROUND5=PASS deleted={len(deleted)} remaining={len(after)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
