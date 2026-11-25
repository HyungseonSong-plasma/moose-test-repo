"""Pure Git tree decoding and SHA-1 blob identity primitives."""
from __future__ import annotations

from collections.abc import Iterator
import hashlib


def regular_tree_paths(data: bytes) -> Iterator[str]:
    """Decode NUL-delimited ls-tree output, retaining regular blobs only.

    Preserve order and exact UTF-8 path spelling. The caller validates
    revision, path policy and domain scope.
    """
    for row in data.split(b"\0"):
        if not row:
            continue
        meta, filename = row.split(b"\t", 1)
        mode, kind, _ = meta.decode("ascii").split()
        if kind == "blob" and mode in {"100644", "100755"}:
            yield filename.decode("utf-8", "strict")


def parse_long_tree_row(row: bytes) -> tuple[str, str, str, str, str]:
    """Decode one ls-tree -l row; preserve raw size ('-' for gitlinks).

    Return mode, kind, object SHA, size text, filename. Caller owns object
    type validation, normalization, duplicate detection and error mapping.
    """
    meta, filename = row.split(b"\t", 1)
    mode, kind, sha, size = meta.decode("ascii").split()
    return mode, kind, sha, size, filename.decode("utf-8", "strict")


def git_blob_sha1(data: bytes) -> str:
    """Compute the Git SHA-1 blob object identity, not a plain file hash."""
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


__all__ = ["regular_tree_paths", "parse_long_tree_row", "git_blob_sha1"]
