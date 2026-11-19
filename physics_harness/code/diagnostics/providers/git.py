"""Exact-HEAD, read-only Git tracked-source provider (no worktree fallback)."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

from ..collector import SourceRecord
from ..request import ScanRequest, normalized_path


class GitSourceProvider:
    """Pin inventory and file bytes to HEAD's immutable Git object identities."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _git(self, *args: str) -> bytes:
        result = subprocess.run(
            ["git", "-C", str(self.root), *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=30,
        )
        if result.returncode:
            raise ValueError("GIT_SOURCE_UNAVAILABLE: " +
                             result.stderr.decode("utf-8", "replace").strip()[:250])
        return result.stdout

    def assert_head(self, revision: str) -> None:
        actual = self._git("rev-parse", "--verify", "HEAD").decode("ascii").strip()
        if actual.lower() != revision.lower():
            raise ValueError("GIT_HEAD_MISMATCH")

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
                meta, filename = row.split(b"\t", 1)
                mode, typ, sha, size = meta.decode("ascii").split()
                path = filename.decode("utf-8", "strict")
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
        actual = hashlib.sha1(
            b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        ).hexdigest()
        if actual != record.blob_sha or len(data) != record.size:
            raise ValueError("GIT_SOURCE_BLOB_MISMATCH")
        return data


__all__ = ["GitSourceProvider"]
