"""Read-only evidence from a trusted, complete local SHA-1 Git repository.

No fetch, checkout, credential, remote ref authority or mutation. The runtime
must independently authenticate the checkout, enrolled heads and proof ports.
Linear PR history only; merge/rebase history needs separate qualification.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess

from .controller_merge_reconciliation import TreeEntry, TreeSnapshot, PRMergeSource
from .controller_pr_state import PRStateHold

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_ROOT = "automation/controller-state/"
_MAX_COMMITS = 10_000
_MAX_BLOB = 64 * 1024 * 1024
_MAX_TREE_BYTES = 64 * 1024 * 1024


class GitEvidence:
    def __init__(self, repository: Path):
        self.repository = Path(repository).resolve(strict=True)
        if not self.repository.is_dir():
            raise PRStateHold("INVALID_GIT_REPOSITORY")
        if self._git("rev-parse", "--show-object-format").strip() != b"sha1":
            raise PRStateHold("UNSUPPORTED_OBJECT_FORMAT")
        if self._git("rev-parse", "--is-shallow-repository").strip() != b"false":
            raise PRStateHold("SHALLOW_HISTORY")

    def _git(self, *args):
        # No replacement objects, lazy fetch or caller-selected GIT_DIR/index.
        env = {k:v for k,v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0",
                   GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        try:
            result = subprocess.run(["git", "-C", str(self.repository), *args],
                env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            raise PRStateHold("GIT_EVIDENCE_UNAVAILABLE") from exc
        return result.stdout

    @staticmethod
    def _head(value):
        if not isinstance(value, str) or not _SHA.fullmatch(value):
            raise PRStateHold("INVALID_EXACT_GIT_HEAD")
        return value

    def tree(self, head: str) -> TreeSnapshot:
        head = self._head(head)
        if self._git("cat-file", "-t", head).strip() != b"commit":
            raise PRStateHold("NOT_A_COMMIT")
        rows = self._git("ls-tree", "-rz", "--full-tree", head)
        if len(rows) > _MAX_TREE_BYTES:
            raise PRStateHold("TREE_INVENTORY_LIMIT")
        entries = {}
        for row in rows.split(b"\0"):
            if not row:
                continue
            meta, rawpath = row.split(b"\t", 1)
            mode, kind, oid = meta.decode("ascii").split()
            path = rawpath.decode("utf-8", errors="strict")
            self._head(oid)
            if path in entries:
                raise PRStateHold("DUPLICATE_TREE_PATH")
            if mode == "160000" and kind == "commit":
                # Gitlinks store a commit OID, not the submodule's tree bytes.
                digest = sha256(oid.encode("ascii")).hexdigest()
            elif mode in {"100644", "100755", "120000"} and kind == "blob":
                size = int(self._git("cat-file", "-s", oid))
                if size > _MAX_BLOB:
                    raise PRStateHold("BLOB_LIMIT")
                blob = self._git("cat-file", "blob", oid)
                if len(blob) != size:
                    raise PRStateHold("BLOB_SIZE_MISMATCH")
                digest = sha256(blob).hexdigest()
            else:
                raise PRStateHold("UNSUPPORTED_TREE_OBJECT")
            entries[path] = TreeEntry(mode, digest)
        return TreeSnapshot(head, entries)

    def verify_tree(self, snapshot: TreeSnapshot) -> bool:
        return self.tree(snapshot.head) == snapshot

    def _changes(self, parent, head):
        raw = self._git("diff-tree", "--no-commit-id", "--name-status", "-r", "-z",
                        "--no-renames", parent, head).split(b"\0")
        if raw[-1] != b"" or len(raw[:-1]) % 2:
            raise PRStateHold("INVALID_DIFF_INVENTORY")
        return [(raw[i].decode("ascii"), raw[i+1].decode("utf-8")) for i in range(0,len(raw)-1,2)]

    def verify_source_history(self, base: TreeSnapshot, source: PRMergeSource) -> bool:
        """Check linear ancestry and every state addition, not just final bytes.

        Enrollment, PR identity, source head freshness and receipts are separate.
        Reject any state-path edit/deletion even if later reverted.
        """
        if source.base_head != base.head or not self.verify_tree(source.tree):
            return False
        head, ancestor = self._head(source.tree.head), self._head(base.head)
        commits = self._git("rev-list", "--reverse", "--max-count="+str(_MAX_COMMITS+1),
                            ancestor+".."+head).decode("ascii").splitlines()
        if not 0 < len(commits) <= _MAX_COMMITS:
            return False
        parent = ancestor
        observed = []
        for commit in commits:
            parents = self._git("rev-list", "--parents", "-n", "1", self._head(commit)).decode().split()
            if parents != [commit,parent]:
                return False
            changes = self._changes(parent, commit)
            state_changes = [(s,p) for s,p in changes if p.startswith(_ROOT)]
            if state_changes:
                if len(changes) != 1:
                    return False
                status,path = state_changes[0]
                if status != "A" or path not in source.records or path in observed:
                    return False
                record = source.records[path]
                if self._git("show", commit+":"+path) != record or json.loads(record)["expected_parent"] != parent:
                    return False
                observed.append(path)
            parent = commit
        return parent == head and observed == sorted(source.records)
