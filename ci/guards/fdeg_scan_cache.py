"""Exact-HEAD local FDEG scan reuse. Performance data, never authorization evidence.

Cache entries are produced from one *complete* Structural scan and are reused only
on the same clean tracked Git HEAD, same repository root, same target, same
scanner implementation and Python interpreter. Missing/corrupt entries trigger
a fresh scan; the persisted result never promotes scope or SAFE_DELETE.
"""
from __future__ import annotations

import gzip
import io
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
        if not isinstance(record, dict):
            return None
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


SOURCE_SCHEMA = "fdeg.tracked_source_index.v0.1"


def source_index_key(root: Path, head: str | None,
                     implementation_files: tuple[Path, ...]) -> CacheKey | None:
    key = cache_key(root, head, "__TRACKED_SOURCES__", implementation_files)
    if key is None:
        return None
    return CacheKey(key.path.with_name(
        key.path.name.replace("structural-", "sources-") + ".gz"), key.identity)


def load_source_index(key: CacheKey, git_blob_manifest: dict[str, str]
                      ) -> tuple[dict[str, tuple[str, str]], list[dict]] | None:
    """Load one complete source snapshot for *all* target-specific cold scans.

    No subset of paths is silently dropped: the first scan must have enumerated
    the entire tracked input set and persisted its errors alongside source data.
    """
    try:
        if key.path.is_symlink() or not key.path.is_file():
            return None
        if key.path.stat().st_size > MAX_CACHE_BYTES:
            return None
        with gzip.GzipFile(fileobj=io.BytesIO(key.path.read_bytes())) as stream:
            raw = stream.read(4 * MAX_CACHE_BYTES + 1)
        if len(raw) > 4 * MAX_CACHE_BYTES:
            return None
        record = json.loads(raw)
        if not isinstance(record, dict):
            return None
        if (record.get("schema") != SOURCE_SCHEMA
                or record.get("key") != key.identity):
            return None
        payload = record.get("payload")
        if (not isinstance(payload, dict)
                or not isinstance(payload.get("contents"), dict)
                or not isinstance(payload.get("errors"), list)
                or digest(canonical(payload)) != record.get("payload_sha256")):
            return None
        contents = {}
        for name, value in payload["contents"].items():
            if (not isinstance(name, str) or not isinstance(value, list)
                    or len(value) != 2 or not all(isinstance(x, str) for x in value)):
                return None
            contents[name] = (value[0], value[1])
        # The cache's own SHA-256 is not a completeness oracle. Cross-check
        # *every* expected tracked path/blob against the HEAD's Git index;
        # this rejects a rehashed-but-omitted file or forged source value.
        if not all(isinstance(e, dict) and isinstance(e.get("path"), str)
                   for e in payload["errors"]):
            return None
        failed_paths = {e["path"] for e in payload["errors"]}
        if (set(contents) & failed_paths
                or set(contents) | failed_paths != set(git_blob_manifest)):
            return None
        for path, (text, sha) in contents.items():
            encoded = text.encode("utf-8")
            actual_sha = hashlib.sha1(
                b"blob " + str(len(encoded)).encode() + b"\0" + encoded).hexdigest()
            if sha != actual_sha or sha != git_blob_manifest[path]:
                return None
        return contents, payload["errors"]
    except (OSError, ValueError, TypeError, KeyError, EOFError, UnicodeError):
        return None


def save_source_index(key: CacheKey, contents: dict[str, tuple[str, str]],
                      errors: list[dict]) -> bool:
    temp_name: str | None = None
    try:
        key.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = {"contents": contents, "errors": errors}
        doc = {"schema": SOURCE_SCHEMA, "key": key.identity,
               "payload": payload, "payload_sha256": digest(canonical(payload))}
        compressed = gzip.compress(canonical(doc) + b"\n", compresslevel=3, mtime=0)
        if len(compressed) > MAX_CACHE_BYTES:
            return False
        with tempfile.NamedTemporaryFile(prefix=".fdeg-source-",
                                        suffix=".tmp", dir=key.path.parent,
                                        delete=False) as writer:
            temp_name = writer.name
            writer.write(compressed)
        os.replace(temp_name, key.path)
        return True
    except (OSError, ValueError, TypeError):
        return False
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
