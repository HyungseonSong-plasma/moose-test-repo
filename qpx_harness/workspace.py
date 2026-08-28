"""Static QPX workspace discovery, inventory, and comparison utilities."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

VALID_TEST_TYPES = {"canonical", "diagnostic"}

GENERATED_DIR_NAMES = {
    ".jitcache",
    "__pycache__",
    "checkpoint",
    "checkpoints",
    "result",
    "results",
    "output",
    "outputs",
}
GENERATED_SUFFIXES = {".log", ".csv", ".e", ".exo", ".out", ".bak", ".tmp", ".pyc", ".pyo"}
GENERATED_BASENAMES = {".DS_Store", "prepare_evidence.json", "suite_summary.json"}
TEXT_SUFFIXES = {".py", ".json", ".txt", ".md", ".i", ".sh", ".yaml", ".yml", ".toml", ".cfg"}
MANIFEST_IDENTITY_KEYS = ("name", "test_name", "id")


@dataclass(frozen=True)
class WorkspaceFile:
    relative_path: str
    size: int
    sha256: str
    generated_candidate: bool
    manifest_identity: str | None = None


@dataclass(frozen=True)
class ManifestStatus:
    path: str
    test_type: str | None
    json_ok: bool
    input_name: str | None
    input_state: str | None
    checker: str | None
    checker_resolves: bool | None
    prepare: str | None
    prepare_resolves: bool | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        if not self.json_ok:
            return False
        if self.test_type not in VALID_TEST_TYPES:
            return False
        if self.checker_resolves is False or self.prepare_resolves is False:
            return False
        return self.input_state != "missing"


@dataclass(frozen=True)
class WorkspaceInventory:
    root: str
    files: tuple[WorkspaceFile, ...]
    manifests: tuple[ManifestStatus, ...]


@dataclass(frozen=True)
class ComparisonRecord:
    source_path: str
    source_sha256: str
    source_size: int
    generated_candidate: bool
    relationship: str
    target_paths: tuple[str, ...]
    manifest_identity: str | None = None


@dataclass(frozen=True)
class WorkspaceComparison:
    source_root: str
    target_root: str
    records: tuple[ComparisonRecord, ...]

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(record.relationship for record in self.records))


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(case_dir: Path) -> dict:
    manifest = Path(case_dir) / "test.json"
    if not manifest.is_file():
        raise SystemExit(f"missing test manifest: {manifest}")
    return json.loads(manifest.read_text())


def manifest_type(manifest: Path) -> str:
    cfg = json.loads(Path(manifest).read_text())
    test_type = cfg.get("type", "canonical")
    if test_type not in VALID_TEST_TYPES:
        raise SystemExit(f"invalid test type {test_type!r} in {manifest}")
    return test_type


def discover_manifests(
    roots: Iterable[Path],
    *,
    on_missing_root: Callable[[Path], None] | None = None,
) -> list[Path]:
    manifests: list[Path] = []
    seen: set[str] = set()
    for raw_root in roots:
        root = Path(raw_root).expanduser().resolve()
        if not root.exists():
            if on_missing_root is not None:
                on_missing_root(root)
            continue
        for manifest in sorted(root.rglob("test.json")):
            key = str(manifest.resolve())
            if key not in seen:
                seen.add(key)
                manifests.append(manifest.resolve())
    return manifests


def _manifest_identity(path: Path) -> str | None:
    if path.name != "test.json":
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    for key in MANIFEST_IDENTITY_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def is_generated_candidate(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    parts_lower = {part.lower() for part in rel.parts}
    if any(name.lower() in parts_lower for name in GENERATED_DIR_NAMES):
        return True
    if path.name in GENERATED_BASENAMES:
        return True
    if path.suffix.lower() in GENERATED_SUFFIXES:
        return True
    name = path.name.lower()
    if "_out" in name and path.suffix.lower() in {".csv", ".e", ".exo"}:
        return True
    if re.search(r"(?:^|/)[^/]*_cp(?:/|$)", rel.as_posix().lower()):
        return True
    return False


def validate_manifest(manifest: Path) -> ManifestStatus:
    manifest = Path(manifest).resolve()
    case_dir = manifest.parent
    try:
        cfg = json.loads(manifest.read_text())
        if not isinstance(cfg, dict):
            raise ValueError("manifest JSON must be an object")
    except Exception as exc:
        return ManifestStatus(
            path=str(manifest),
            test_type=None,
            json_ok=False,
            input_name=None,
            input_state=None,
            checker=None,
            checker_resolves=None,
            prepare=None,
            prepare_resolves=None,
            error=str(exc),
        )

    test_type = cfg.get("type", "canonical")
    input_name = cfg.get("input") if isinstance(cfg.get("input"), str) else None
    checker = cfg.get("checker") if isinstance(cfg.get("checker"), str) else None
    prepare = cfg.get("prepare") if isinstance(cfg.get("prepare"), str) else None

    prepare_resolves = (case_dir / prepare).resolve().is_file() if prepare else None
    checker_resolves = (case_dir / checker).resolve().is_file() if checker else None

    if input_name:
        input_path = (case_dir / input_name).resolve()
        if input_path.is_file():
            input_state = "present"
        elif prepare and prepare_resolves:
            input_state = "generated_by_prepare"
        else:
            input_state = "missing"
    else:
        input_state = "missing"

    error = None
    if test_type not in VALID_TEST_TYPES:
        error = f"invalid test type: {test_type!r}"

    return ManifestStatus(
        path=str(manifest),
        test_type=test_type,
        json_ok=True,
        input_name=input_name,
        input_state=input_state,
        checker=checker,
        checker_resolves=checker_resolves,
        prepare=prepare,
        prepare_resolves=prepare_resolves,
        error=error,
    )


def inventory_workspace(root: Path) -> WorkspaceInventory:
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"workspace root does not exist: {root}")

    files: list[WorkspaceFile] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        files.append(
            WorkspaceFile(
                relative_path=path.relative_to(root).as_posix(),
                size=path.stat().st_size,
                sha256=hash_file(path),
                generated_candidate=is_generated_candidate(path, root),
                manifest_identity=_manifest_identity(path),
            )
        )

    manifests = tuple(validate_manifest(path) for path in discover_manifests([root]))
    return WorkspaceInventory(root=str(root), files=tuple(files), manifests=manifests)


def summarize_workspace(inventory: WorkspaceInventory) -> dict:
    canonical = sum(1 for item in inventory.manifests if item.test_type == "canonical")
    diagnostic = sum(1 for item in inventory.manifests if item.test_type == "diagnostic")
    invalid = [item.path for item in inventory.manifests if not item.ok]
    generated = sum(1 for item in inventory.files if item.generated_candidate)
    return {
        "root": inventory.root,
        "file_count": len(inventory.files),
        "manifest_count": len(inventory.manifests),
        "canonical_count": canonical,
        "diagnostic_count": diagnostic,
        "generated_candidate_count": generated,
        "invalid_manifest_count": len(invalid),
        "invalid_manifests": invalid,
    }


def compare_workspaces(source: WorkspaceInventory, target: WorkspaceInventory) -> WorkspaceComparison:
    target_by_hash: dict[str, list[WorkspaceFile]] = defaultdict(list)
    target_by_rel: dict[str, list[WorkspaceFile]] = defaultdict(list)
    target_manifest_by_identity: dict[str, list[WorkspaceFile]] = defaultdict(list)

    for item in target.files:
        target_by_hash[item.sha256].append(item)
        target_by_rel[item.relative_path].append(item)
        if item.manifest_identity:
            target_manifest_by_identity[item.manifest_identity].append(item)

    records: list[ComparisonRecord] = []
    for item in source.files:
        hash_matches = target_by_hash.get(item.sha256, [])
        rel_matches = target_by_rel.get(item.relative_path, [])
        identity_matches = (
            target_manifest_by_identity.get(item.manifest_identity, [])
            if item.manifest_identity
            else []
        )

        if hash_matches:
            relationship = "EXACT_DUPLICATE"
            matches = hash_matches
        elif rel_matches:
            relationship = "SAME_RELATIVE_PATH_DIFFERENT_BYTES"
            matches = rel_matches
        elif identity_matches:
            relationship = "SAME_MANIFEST_IDENTITY_DIFFERENT_BYTES"
            matches = identity_matches
        else:
            relationship = "SOURCE_ONLY"
            matches = []

        records.append(
            ComparisonRecord(
                source_path=item.relative_path,
                source_sha256=item.sha256,
                source_size=item.size,
                generated_candidate=item.generated_candidate,
                relationship=relationship,
                target_paths=tuple(match.relative_path for match in matches),
                manifest_identity=item.manifest_identity,
            )
        )

    return WorkspaceComparison(
        source_root=source.root,
        target_root=target.root,
        records=tuple(records),
    )


def find_text_references(root: Path, needle: str) -> tuple[str, ...]:
    root = Path(root).expanduser().resolve()
    hits: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(errors="replace")
        except Exception:
            continue
        if needle in text:
            hits.append(path.relative_to(root).as_posix())
    return tuple(hits)


def inventory_to_dict(inventory: WorkspaceInventory) -> dict:
    return {
        "summary": summarize_workspace(inventory),
        "files": [asdict(item) for item in inventory.files],
        "manifests": [asdict(item) | {"ok": item.ok} for item in inventory.manifests],
    }


def comparison_to_dict(comparison: WorkspaceComparison) -> dict:
    return {
        "source_root": comparison.source_root,
        "target_root": comparison.target_root,
        "counts": comparison.counts,
        "records": [asdict(item) for item in comparison.records],
    }


def inventory_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qpx inventory")
    parser.add_argument("root", help="workspace root to inventory")
    parser.add_argument("--compare-to", help="second workspace root for byte/path comparison")
    parser.add_argument("--find-reference", action="append", default=[])
    parser.add_argument("--json-out")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    inventory = inventory_workspace(Path(args.root))
    summary = summarize_workspace(inventory)
    payload: dict = {"inventory": inventory_to_dict(inventory)}

    print("QPX WORKSPACE INVENTORY")
    print(f"ROOT        {summary['root']}")
    print(f"FILES       {summary['file_count']}")
    print(f"MANIFESTS   {summary['manifest_count']}")
    print(f"CANONICAL   {summary['canonical_count']}")
    print(f"DIAGNOSTIC  {summary['diagnostic_count']}")
    print(f"GENERATED?  {summary['generated_candidate_count']}")
    print(f"INVALID     {summary['invalid_manifest_count']}")

    if args.compare_to:
        target = inventory_workspace(Path(args.compare_to))
        comparison = compare_workspaces(inventory, target)
        payload["comparison"] = comparison_to_dict(comparison)
        print()
        print(f"COMPARE_TO  {target.root}")
        for key, value in sorted(comparison.counts.items()):
            print(f"{key:<40} {value}")

    if args.find_reference:
        refs = {}
        print()
        for needle in args.find_reference:
            hits = find_text_references(Path(args.root), needle)
            refs[needle] = list(hits)
            print(f"REFERENCE {needle!r}: {len(hits)}")
        payload["references"] = refs

    if args.json_out:
        out = Path(args.json_out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"JSON        {out}")

    if args.strict and summary["invalid_manifest_count"]:
        return 1
    return 0


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        left = base / "left"
        right = base / "right"
        (left / "Issue1_a").mkdir(parents=True)
        (right / "Issue9_copy").mkdir(parents=True)
        (right / "Issue1_a").mkdir(parents=True)

        input_text = "[Mesh]\n  type = GeneratedMesh\n[]\n"
        (left / "Issue1_a" / "input.i").write_text(input_text)
        (left / "Issue1_a" / "check.py").write_text("raise SystemExit(0)\n")
        (left / "Issue1_a" / "run.log").write_text("generated\n")
        (left / "Issue1_a" / "test.json").write_text(json.dumps({
            "name": "case_a",
            "type": "canonical",
            "input": "input.i",
            "checker": "check.py",
        }))

        (right / "Issue9_copy" / "input.i").write_text(input_text)
        (right / "Issue9_copy" / "check.py").write_text("raise SystemExit(0)\n")

        (right / "Issue1_a" / "run.log").write_text("different\n")
        (right / "Issue1_a" / "test.json").write_text(json.dumps({
            "name": "case_a",
            "type": "canonical",
            "input": "created.i",
            "prepare": "prepare.py",
        }))
        (right / "Issue1_a" / "prepare.py").write_text(
            "from pathlib import Path\nPath('created.i').write_text('ok')\n"
        )

        (left / "Issue2_b").mkdir(parents=True)
        (right / "Issue8_b").mkdir(parents=True)
        (left / "Issue2_b" / "left.i").write_text("left\n")
        (right / "Issue8_b" / "right.i").write_text("right\n")
        (left / "Issue2_b" / "test.json").write_text(json.dumps({
            "name": "case_b",
            "type": "diagnostic",
            "input": "left.i",
        }))
        (right / "Issue8_b" / "test.json").write_text(json.dumps({
            "name": "case_b",
            "type": "diagnostic",
            "input": "right.i",
        }))

        left_inv = inventory_workspace(left)
        right_inv = inventory_workspace(right)
        left_summary = summarize_workspace(left_inv)
        right_summary = summarize_workspace(right_inv)
        comparison = compare_workspaces(left_inv, right_inv)

        checks = [
            left_summary["canonical_count"] == 1,
            left_summary["invalid_manifest_count"] == 0,
            right_summary["canonical_count"] == 1,
            right_summary["invalid_manifest_count"] == 0,
            any(r.relationship == "EXACT_DUPLICATE" for r in comparison.records),
            any(r.relationship == "SAME_RELATIVE_PATH_DIFFERENT_BYTES" for r in comparison.records),
            any(r.relationship == "SAME_MANIFEST_IDENTITY_DIFFERENT_BYTES" for r in comparison.records),
            any(f.generated_candidate for f in left_inv.files if f.relative_path.endswith("run.log")),
        ]

    ok = all(checks)
    print("QPX_WORKSPACE_SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1
