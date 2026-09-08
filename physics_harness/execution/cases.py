"""Reusable case staging and input-asset validation primitives.

This module owns filesystem mechanics only. Callers own experiment names,
artifact patterns, input semantics, and scientific interpretation.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Iterable


class CaseError(RuntimeError):
    pass


_FILE_PARAM_RE = re.compile(
    r"""^\s*(?P<name>file|[A-Za-z_][A-Za-z0-9_]*_file)\s*=\s*
        (?:
          '(?P<single>[^']+)'
          |
          \"(?P<double>[^\"]+)\"
          |
          (?P<bare>[^\s#]+)
        )
    """,
    re.MULTILINE | re.VERBOSE,
)


def _direct_child_name(name: str, *, label: str) -> str:
    raw = str(name)
    path = Path(raw)
    if not raw or raw in {".", ".."} or path.name != raw:
        raise CaseError(f"{label} must be a direct-child name: {raw!r}")
    return raw


def _relative_label(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def purge_generated_artifacts(
    root: Path,
    *,
    directory_names: Iterable[str] = (),
    patterns: Iterable[str] = (),
) -> tuple[str, ...]:
    root = Path(root)
    if not root.is_dir():
        raise CaseError(f"case root does not exist: {root}")
    candidates: dict[str, Path] = {}
    for raw_name in directory_names:
        name = _direct_child_name(str(raw_name), label="generated directory name")
        for path in root.rglob(name):
            if path.is_dir():
                candidates[str(path.resolve())] = path
    for raw_pattern in patterns:
        pattern = str(raw_pattern)
        if not pattern:
            raise CaseError("generated artifact pattern must be non-empty")
        for path in root.rglob(pattern):
            if path != root and (path.is_file() or path.is_dir()):
                candidates[str(path.resolve())] = path
    removed: list[str] = []
    ordered = sorted(
        candidates.values(),
        key=lambda item: (len(item.parts), item.as_posix()),
        reverse=True,
    )
    for path in ordered:
        if not path.exists():
            continue
        removed.append(_relative_label(path, root))
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    return tuple(sorted(removed))


def stage_case(
    source: Path,
    target: Path,
    *,
    input_text: str | None = None,
    input_name: str = "input.i",
    purge_directory_names: Iterable[str] = (),
    purge_patterns: Iterable[str] = (),
) -> dict[str, object]:
    source = Path(source)
    target = Path(target)
    if not source.is_dir():
        raise CaseError(f"case source does not exist: {source}")
    if target.exists():
        raise CaseError(f"case target already exists: {target}")
    safe_input_name = _direct_child_name(input_name, label="input name")
    shutil.copytree(source, target)
    purged = purge_generated_artifacts(
        target,
        directory_names=purge_directory_names,
        patterns=purge_patterns,
    )
    input_path = target / safe_input_name
    if input_text is not None:
        input_path.write_text(str(input_text))
    return {
        "source": str(source.resolve()),
        "target": str(target.resolve()),
        "input": str(input_path.resolve()),
        "input_replaced": input_text is not None,
        "purged": list(purged),
    }


def referenced_file_parameters(
    input_text: str,
    case_dir: Path,
    *,
    skip_dynamic: bool = False,
) -> list[dict[str, str]]:
    case_dir = Path(case_dir)
    refs: list[dict[str, str]] = []
    for match in _FILE_PARAM_RE.finditer(str(input_text)):
        raw = match.group("single") or match.group("double") or match.group("bare") or ""
        if not raw:
            continue
        if skip_dynamic and "${" in raw:
            continue
        path = Path(raw).expanduser()
        resolved = path if path.is_absolute() else case_dir / path
        refs.append(
            {
                "parameter": match.group("name"),
                "raw": raw,
                "resolved": str(resolved.resolve()),
            }
        )
    return refs


def validate_referenced_files(
    input_text: str,
    case_dir: Path,
    *,
    skip_dynamic: bool = False,
) -> list[dict[str, str]]:
    refs = referenced_file_parameters(
        input_text,
        case_dir,
        skip_dynamic=skip_dynamic,
    )
    missing = [ref for ref in refs if not Path(ref["resolved"]).is_file()]
    if missing:
        detail = ", ".join(
            f"{ref['parameter']}={ref['resolved']}" for ref in missing
        )
        raise CaseError(f"missing referenced input file(s): {detail}")
    return refs


def validate_case_references(
    case_dir: Path,
    *,
    input_name: str = "input.i",
    skip_dynamic: bool = False,
) -> list[dict[str, str]]:
    case_dir = Path(case_dir)
    safe_input_name = _direct_child_name(input_name, label="input name")
    input_path = case_dir / safe_input_name
    if not input_path.is_file():
        raise CaseError(f"case input does not exist: {input_path}")
    return validate_referenced_files(
        input_path.read_text(),
        case_dir,
        skip_dynamic=skip_dynamic,
    )
