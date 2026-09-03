"""Declarative experiment specification loaded by the canonical qpx gateway."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

SUPPORTED_CASE_FORMATS = {"parquet", "ipc", "feather", "ndjson", "csv"}


@dataclass(frozen=True)
class CaseSource:
    path: Path
    format: str


@dataclass(frozen=True)
class ExperimentSpec:
    schema_version: int
    experiment_id: str
    protocol: str
    source_path: Path
    execution: Mapping[str, Any] = field(default_factory=dict)
    parameters: Mapping[str, Any] = field(default_factory=dict)
    outputs: Mapping[str, Any] = field(default_factory=dict)
    case_source: CaseSource | None = None

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if path.is_absolute():
            return path
        return (self.source_path.parent / path).resolve()


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _case_source(raw: Any, *, base: Path) -> CaseSource | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("case_source must be a JSON object")
    path_raw = raw.get("path")
    if not isinstance(path_raw, str) or not path_raw.strip():
        raise ValueError("case_source.path must be a non-empty string")
    fmt = str(raw.get("format") or Path(path_raw).suffix.lstrip(".")).lower()
    if fmt == "jsonl":
        fmt = "ndjson"
    if fmt not in SUPPORTED_CASE_FORMATS:
        raise ValueError("case_source.format must be one of " + ", ".join(sorted(SUPPORTED_CASE_FORMATS)))
    path = Path(path_raw).expanduser()
    if not path.is_absolute():
        path = (base / path).resolve()
    return CaseSource(path=path, format=fmt)


def load_experiment_spec(path: str | Path) -> ExperimentSpec:
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() != ".json":
        raise ValueError("experiment control specification must be JSON")
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("experiment specification root must be a JSON object")
    schema_version = raw.get("schema_version")
    if schema_version != 1:
        raise ValueError(f"unsupported experiment schema_version: {schema_version!r}")
    experiment_id = raw.get("experiment_id")
    protocol = raw.get("protocol")
    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ValueError("experiment_id must be a non-empty string")
    if not isinstance(protocol, str) or not protocol.strip():
        raise ValueError("protocol must be a non-empty string")
    return ExperimentSpec(
        schema_version=1,
        experiment_id=experiment_id,
        protocol=protocol,
        source_path=source,
        execution=_mapping(raw.get("execution"), "execution"),
        parameters=_mapping(raw.get("parameters"), "parameters"),
        outputs=_mapping(raw.get("outputs"), "outputs"),
        case_source=_case_source(raw.get("case_source"), base=source.parent),
    )


__all__ = ["CaseSource", "ExperimentSpec", "SUPPORTED_CASE_FORMATS", "load_experiment_spec"]
