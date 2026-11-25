"""Exact-HEAD, read-only Git tracked-source provider (no worktree fallback)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from libs.command_execution.runner import run_command_bytes
from libs.git_evidence.git import git_blob_sha1, parse_long_tree_row, regular_tree_paths

from ..collector import SourceRecord, SourceInput
from ..request import ScanRequest, normalized_path


class GitSourceProvider:
    """Pin inventory and file bytes to HEAD's immutable Git object identities."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _git(self, *args: str) -> bytes:
        result = run_command_bytes(("git", "-C", str(self.root), *args),
                                   timeout_seconds=30)
        if result.returncode:
            raise ValueError("GIT_SOURCE_UNAVAILABLE: " +
                             result.stderr.decode("utf-8", "replace").strip()[:250])
        return result.stdout

    def assert_head(self, revision: str) -> None:
        actual = self._git("rev-parse", "--verify", "HEAD").decode("ascii").strip()
        if actual.lower() != revision.lower():
            raise ValueError("GIT_HEAD_MISMATCH")

    def _regular_tree_paths(self, revision: str) -> Iterator[str]:
        """Read regular blob paths from a caller-validated exact commit.

        No HEAD check, path normalization, domain filtering or consumer error
        translation: those remain the responsibility of the calling operation.
        """
        yield from regular_tree_paths(
            self._git("ls-tree", "--full-tree", "-r", "-z", revision))

    def inventory(self, request: ScanRequest) -> tuple[SourceRecord, ...]:
        if not isinstance(request, ScanRequest):
            raise TypeError("request must be a ScanRequest")
        self.assert_head(request.revision)
        records = []
        rows = self._git("ls-tree", "--full-tree", "-r", "-l", "-z",
                         request.revision).split(b"\0")
        for row in rows:
            if not row:
                continue
            try:
                mode, typ, sha, size, path = parse_long_tree_row(row)
                normalized_path(path)
                if typ not in {"blob", "commit"}:
                    raise ValueError("INVALID_GIT_ENTRY_TYPE")
                records.append(SourceRecord(
                    path=path, blob_sha=sha.lower(), mode=mode,
                    size=0 if size == "-" else int(size),
                ))
            except (UnicodeError, TypeError, IndexError, KeyError) as error:
                raise ValueError("INVALID_GIT_INVENTORY") from error
        paths = [record.path for record in records]
        if len(paths) != len(set(paths)):
            raise ValueError("DUPLICATE_GIT_INVENTORY_PATH")
        return tuple(sorted(records, key=lambda r: r.path))

    def read(self, record: SourceRecord) -> bytes:
        if record.mode not in {"100644", "100755"}:
            raise ValueError("GIT_SOURCE_NON_REGULAR")
        data = self._git("cat-file", "blob", record.blob_sha)
        actual = git_blob_sha1(data)
        if actual != record.blob_sha or len(data) != record.size:
            raise ValueError("GIT_SOURCE_BLOB_MISMATCH")
        return data

    def read_at_revision(self, revision: str, path: str) -> SourceInput:
        """Read one regular tracked file from an exact local Git commit tree.

        Historical commits must exist in the local object database. A shallow
        clone missing the commit fails closed; never reads the worktree as a
        fallback or fetches remote history implicitly. This is *source*
        provenance, not evidence of behavioral/semantic equivalence.
        """
        import re
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("INVALID_HISTORY_REVISION")
        if not isinstance(path, str) or path.startswith(":("):
            raise ValueError("INVALID_HISTORY_PATH")
        try:
            if normalized_path(path) != path:
                raise ValueError("INVALID_HISTORY_PATH")
        except (TypeError, ValueError) as exc:
            raise ValueError("INVALID_HISTORY_PATH") from exc
        if self._git("cat-file", "-t", revision).strip() != b"commit":
            raise ValueError("HISTORY_OBJECT_NOT_COMMIT")
        rows = [row for row in self._git(
            "ls-tree", "--full-tree", "-l", "-z", revision, "--", path
        ).split(b"\0") if row]
        if len(rows) != 1:
            raise ValueError("HISTORY_SOURCE_UNRESOLVED")
        try:
            mode, kind, sha, size, observed = parse_long_tree_row(rows[0])
            if observed != path or kind != "blob" or mode not in {"100644", "100755"}:
                raise ValueError("HISTORY_NOT_REGULAR_FILE")
            record = SourceRecord(path=path, blob_sha=sha.lower(), mode=mode, size=int(size))
        except (ValueError, UnicodeError) as exc:
            raise ValueError("HISTORY_SOURCE_INVALID") from exc
        return SourceInput(record, self.read(record))


__all__ = ["GitSourceProvider"]
