#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

TARGETS = [
  [
    "fix/aikido-security-code-audit-115212587-vr72",
    "765742de0fcee9340eefd5ce231962b6547f8071"
  ],
  [
    "fix/aikido-security-code-audit-115214118-2teg",
    "8b3606fd09e39b46577839d31c7dfdb8131574b2"
  ],
  [
    "harness-dependency-preflight",
    "40a21971af67158f09f8461808613eec43d66ff7"
  ],
  [
    "issue-228-axis-bc-10step",
    "13689874d70d1782ec5e4728ee11e6cca6cb3e07"
  ],
  [
    "issue-228-d1-s2",
    "c7e8efba5ad991cdef79304f53e0aae3b3b6dbc1"
  ],
  [
    "issue-228-d1-s3",
    "e74734f6349a1192d6f3cbc00b90374f74b9799a"
  ],
  [
    "issue-228-e2-w3-w4-s1",
    "b4bba569a73afc806630585b07eedc49f13f646b"
  ],
  [
    "issue-228-face-flux-probe",
    "880d0c1e8d2d001e4e99c15021d10090ea68264f"
  ],
  [
    "issue-228-ion-model-matrix",
    "23488c27be70f75c529e8163d62b3296a612d1a6"
  ],
  [
    "issue-228-p2-e1-w2-pg",
    "ef304dc85f0b11c07a19c210fc5780d3f745d3b0"
  ],
  [
    "issue-228-pgw-parallel",
    "fc3bab84c1944649886b55d89d884e2b4e6b9c16"
  ],
  [
    "issue-228-s4-residual",
    "94a96f5c585fbe86456fc9d2bc8e2cacbf9cda3e"
  ],
  [
    "issue-228-s5-local-bc-ci",
    "811666ef24b49ef79bc6a1f58c4806b3023eb674"
  ],
  [
    "issue-228-s6-directional-observable",
    "9071b1d3ab51cecfe259b6b6ef9a86a8010f6ef4"
  ],
  [
    "issue-228-s6b-baseline-wall-field",
    "714d2b0f4362d4167995f10a44265187a66beee6"
  ],
  [
    "issue-228-wall-av-10step",
    "bc9399bc8de458d67ab4d8f12719bd04057832e7"
  ],
  [
    "issue-236-m1a-multiapp-smoke",
    "6fbeefa55acab15f41dbdecadefb0d7fe7d56ce2"
  ],
  [
    "issue-236-run32-preflight-gate",
    "2eb6c66c251089b0a6604727107babd983543800"
  ],
  [
    "issue-236-transfer-diag-preflight-fix",
    "24dd201bd58770479b5c151f5da024f8d395cc77"
  ],
  [
    "issue-236-transfer-diagnostics",
    "2736105200f16a92520bd060df78b38a9855f638"
  ],
  [
    "issue-242-electron-log-molar-transport",
    "d033d275bffa13262688202a352454cd64a83d7d"
  ],
  [
    "issue-243-t1-log-molar-coupled-particle",
    "d746042323ad3817be80066a58d88f1196c82366"
  ],
  [
    "issue-245-t2-molar-electron-energy",
    "2f2132672acd63fc70db475ddd57125ae93781df"
  ],
  [
    "issue192-p3-diagnostic-matrix",
    "2a42f466871294dd1c04319ea402edf802cddca6"
  ],
  [
    "issue224-build-once-ten-way-fanout",
    "b1b51e431037c74446ff463ed0b68f418b3f6d2b"
  ],
  [
    "issue224-c3-observability-memory",
    "3b2569bbb28a8df1b3d24e966f4ffcc694d028fe"
  ],
  [
    "issue224-c5-observer-family-memory",
    "8179e60bb4fe2eae0342f96e3905d8c20f72aada"
  ],
  [
    "issue224-c5r-os-rss",
    "a0aa0ea3cb86ab8bd1f978c269ad380eadcea558"
  ],
  [
    "issue224-c6-element-aggregate-type-split",
    "875cba854716dcf40916ed8141c9fbf92319cdcf"
  ],
  [
    "issue224-parallel-hypothesis-matrix-design",
    "345977b9e9445fd7e7503eb43c3ba65ee1a50252"
  ],
  [
    "maintenance/physics-opt-doc-naming",
    "ac89afadd96456976c1e6089f146c410e5d49dc8"
  ],
  [
    "probe/runner-1s-20260913",
    "3142e48541be382c846de0e5bb1aadf3c5ac4750"
  ],
  [
    "science-standalone-bundle",
    "db29de6d4fe8035e10db2176d5b1c9f666295a8f"
  ],
  [
    "standard-moose-energy-ab",
    "6b875df183265bf50f909764d73a74a227090298"
  ],
  [
    "standard-moose-energy-retire",
    "5dd5efbacdba99637e0dc6180627237f50b7476e"
  ],
  [
    "tmp-do-not-use",
    "ef98515254b13ca9cb9ee456e48cd4dd4ef74c1e"
  ],
  [
    "work/192-governed-ci-runtime-authority",
    "92af1e43df09d7ec526f341f04a48739b517780b"
  ]
]
ROOT = Path(__file__).resolve().parents[2]
PROV = ROOT / "docs" / "provenance" / "branch-cleanup-2026-09-18"

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
    kept = {k: v for k, v in after.items() if k == "main" or k.startswith("issue-234-")}
    unexpected = {k: v for k, v in after.items() if k != "main" and not k.startswith("issue-234-")}
    write_refs(PROV / "kept.tsv", kept)
    write_refs(PROV / "unexpected-after.tsv", unexpected)
    (PROV / "deleted.tsv").write_text(
        "".join(f"{b}\t{s}\n" for b, s in deleted), encoding="utf-8"
    )
    (PROV / "failed.tsv").write_text(
        "".join(f"{b}\t{e}\t{c}\t{r}\n" for b, e, c, r in failed), encoding="utf-8"
    )
    (PROV / "README.md").write_text(
        "# Branch cleanup provenance\n\n"
        "Date: 2026-09-18\n\n"
        "Policy:\n"
        "- keep `main`;\n"
        "- keep branches owned by currently open Issue #234;\n"
        "- stale PRs #229, #238, and #244 were closed before cleanup because their owning issues are terminal;\n"
        "- delete terminal-issue, probe, maintenance, temporary, and superseded branches;\n"
        "- delete only when the live remote SHA exactly matches the pre-cleanup inventory.\n\n"
        "The exact pre/post refs and deletion results are preserved in this directory.\n",
        encoding="utf-8",
    )

    canonical_guard = run(
        ["git", "show", "HEAD^:tools/workflow/workflow_guard.py"]
    ).stdout
    (ROOT / "tools" / "workflow" / "workflow_guard.py").write_text(
        canonical_guard, encoding="utf-8"
    )
    (ROOT / ".github" / "workflows" / "branch-cleanup-once.yml").unlink(missing_ok=True)
    Path(__file__).unlink(missing_ok=True)

    run(["git", "config", "user.name", "physics-branch-cleanup"])
    run(["git", "config", "user.email", "actions@users.noreply.github.com"])
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "Record branch cleanup provenance"])
    push = run(["git", "push", "origin", "HEAD:main"], check=False)
    if push.returncode != 0:
        sys.stderr.write(push.stdout + push.stderr)
        return 2

    if failed or unexpected or len(deleted) != 37 or len(after) != 18:
        print("BRANCH_CLEANUP=FAIL", file=sys.stderr)
        print(f"deleted={len(deleted)} failed={len(failed)} remaining={len(after)} unexpected={len(unexpected)}", file=sys.stderr)
        return 1

    print(f"BRANCH_CLEANUP=PASS deleted={len(deleted)} remaining={len(after)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
