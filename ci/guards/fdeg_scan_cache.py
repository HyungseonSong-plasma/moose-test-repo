"""Exact-HEAD local FDEG scan reuse. Performance data, never authorization evidence.

Cache entries are produced from one *complete* Structural scan and are reused only
on the same clean tracked Git HEAD, same repository root, same target, same
scanner implementation and Python interpreter. Missing/corrupt entries trigger
a fresh scan; the persisted result never promotes scope or SAFE_DELETE.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import NamedTuple

SCHEMA = "fdeg.structural_scan_cache.v0.1"
MAX_CACHE_BYTES = 64 * 1024 * 1024


class CacheKey(NamedTuple):
    path: Path
    identity: dict


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def cache_key(root: Path, head: str | None, target: str,
              implementation_files: tuple[Path, ...]) -> CacheKey | None:
    env = os.environ.get("FDEG_CACHE_DIR")
    if not env or not head or not (root / ".git").exists():
        return None
    store = Path(env).expanduser()
    if not store.is_absolute():
        return None  # No implicit working-tree write paths.
    store = store.resolve()
    if store == root or root in store.parents:
        return None  # Do not make the scan dirty by writing inside Git.
    fingerprint = digest(canonical({
        str(path.resolve()): digest(path.read_bytes())
        for path in implementation_files
    }))
    identity = {
        "schema": SCHEMA, "repository_root": str(root),
        "repository_head": head, "target": target,
        "scanner_code_sha256": fingerprint,
        "python_implementation": sys.implementation.name,
        "python_version": list(sys.version_info[:3]),
    }
    filename = "structural-" + digest(canonical(identity)) + ".json"
    return CacheKey(store / filename, identity)


def load(key: CacheKey, target: str, head: str, schema: str,
         graph_id) -> dict | None:
    """Verify envelope integrity and graph hash, else force a source rescan."""
    try:
        if key.path.is_symlink() or not key.path.is_file():
            return None
        if key.path.stat().st_size > MAX_CACHE_BYTES:
            return None
        raw = key.path.read_bytes()
        record = json.loads(raw)
        if (record.get("key") != key.identity
                or record.get("schema") != SCHEMA):
            return None
        report = record.get("report")
        if not isinstance(report, dict):
            return None
        if (report.get("schema") != schema
                or report.get("target") != target
                or report.get("repository_head") != head):
            return None
        if digest(canonical(report)) != record.get("payload_sha256"):
            return None
        body = {name: value for name, value in report.items()
                if name != "graph_id"}
        if graph_id("graph", body) != report.get("graph_id"):
            return None
        if report.get("safety") != "NO_CALLER_ZERO_OR_RETIREMENT_VERDICT":
            return None
        return report
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        return None


def save(key: CacheKey, report: dict) -> bool:
    """Atomic local cache; failure is harmless and cannot suppress scanning."""
    tmp: str | None = None
    try:
        key.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        value = {
            "schema": SCHEMA, "key": key.identity,
            "report": report, "payload_sha256": digest(canonical(report)),
        }
        encoded = canonical(value) + b"\n"
        if len(encoded) > MAX_CACHE_BYTES:
            return False
        with tempfile.NamedTemporaryFile(
                prefix=".fdeg-", suffix=".tmp", dir=key.path.parent,
                delete=False) as handle:
            tmp = handle.name
            handle.write(encoded)
        os.replace(tmp, key.path)
        return True
    except (OSError, TypeError, ValueError):
        return False
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
