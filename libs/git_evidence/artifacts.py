"""Bounded ZIP member reads without extraction or domain interpretation."""
from __future__ import annotations

from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile


def read_actions_archive_members(
    archive: bytes, *, entries: tuple[str, ...] | None = None,
    suffix: str | None = None, max_member_bytes: int = 8_000_000,
    max_total_bytes: int = 20_000_000,
) -> dict[str, bytes]:
    """Read exact bounded members without extracting to disk.

    A suffix selector is permitted only for a unique matching member (legacy
    JUnit use). Generated input callers supply explicit member paths.
    """
    if not isinstance(archive, bytes) or len(archive) > 20_000_000:
        raise ValueError("ARCHIVE_COMPRESSED_SIZE_LIMIT")
    if (type(max_member_bytes) is not int or not 1 <= max_member_bytes <= 8_000_000
            or type(max_total_bytes) is not int or not 1 <= max_total_bytes <= 20_000_000):
        raise ValueError("ARCHIVE_LIMIT_INVALID")
    if entries is not None and (not isinstance(entries, tuple) or not entries
            or any(not isinstance(x, str) or not x for x in entries)
            or len(set(entries)) != len(entries)):
        raise ValueError("ARCHIVE_MEMBER_SELECTOR_INVALID")
    if entries is None and (not isinstance(suffix, str) or not suffix):
        raise ValueError("ARCHIVE_MEMBER_SELECTOR_REQUIRED")
    try:
        with ZipFile(BytesIO(archive)) as z:
            items = z.infolist()
            if not items or len(items) > 100:
                raise ValueError("INVALID_ARCHIVE_ENTRY_COUNT")
            names = set()
            available = {}
            total = 0
            for item in items:
                name = item.filename
                parts = name.rstrip("/").split("/")
                if (name.startswith("/") or "\\" in name or "\x00" in item.orig_filename
                        or any(part in {"", ".", ".."} for part in parts)
                        or re.match(r"^[A-Za-z]:", name)):
                    raise ValueError("UNSAFE_ARCHIVE_ENTRY_PATH")
                if name in names:
                    raise ValueError("DUPLICATE_ARCHIVE_ENTRY")
                names.add(name)
                mode = (item.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise ValueError("ARCHIVE_SYMLINK_UNSUPPORTED")
                if mode not in {0, 0o100000, 0o040000}:
                    raise ValueError("ARCHIVE_SPECIAL_ENTRY_UNSUPPORTED")
                if item.flag_bits & 1:
                    raise ValueError("ARCHIVE_ENCRYPTED_ENTRY")
                if item.file_size > max_member_bytes:
                    raise ValueError("ARCHIVE_ENTRY_SIZE_LIMIT")
                total += item.file_size
                if total > max_total_bytes:
                    raise ValueError("ARCHIVE_TOTAL_SIZE_LIMIT")
                if not item.is_dir():
                    available[name] = item
            if entries is None:
                candidates = tuple(n for n in available if n.lower().endswith(suffix.lower()))
                if len(candidates) != 1:
                    raise ValueError("ARCHIVE_MEMBER_AMBIGUOUS_OR_MISSING")
                entries = candidates
            if any(n not in available or (suffix is not None and
                    not n.lower().endswith(suffix.lower())) for n in entries):
                raise ValueError("ARCHIVE_MEMBER_AMBIGUOUS_OR_MISSING")
            result = {}
            for name in entries:
                with z.open(available[name], "r") as handle:
                    data = handle.read(max_member_bytes + 1)
                if len(data) > max_member_bytes or len(data) != available[name].file_size:
                    raise ValueError("ARCHIVE_MEMBER_SIZE_MISMATCH")
                result[name] = data
            return result
    except (BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError("INVALID_ACTIONS_ARTIFACT_ZIP") from exc


__all__ = ["read_actions_archive_members"]
