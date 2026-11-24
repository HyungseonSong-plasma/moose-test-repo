"""Immutable, bounded source-scanning request for Code Diagnostics v0.1."""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import PurePosixPath
import re


_HEX_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")


def normalized_path(value: str, *, allow_pattern: bool = False) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("INVALID_SOURCE_PATH")
    path = PurePosixPath(value)
    if (path.is_absolute() or path.as_posix() != value
            or value in {".", ".."} or ".." in path.parts or "\\" in value):
        raise ValueError("INVALID_SOURCE_PATH")
    if not allow_pattern and any(c in value for c in "*?["):
        raise ValueError("SOURCE_PATH_MUST_BE_LITERAL")
    return value


@dataclass(frozen=True, slots=True)
class ScanBudget:
    max_files: int = 100
    max_bytes: int = 5_000_000
    max_seconds: float = 30.0

    def __post_init__(self) -> None:
        for key in ("max_files", "max_bytes"):
            value = getattr(self, key)
            if type(value) is not int or value < 1:
                raise ValueError(f"{key} must be a positive integer")
        if (type(self.max_seconds) not in (int, float)
                or not 0 < self.max_seconds <= 3600):
            raise ValueError("max_seconds must be in (0, 3600]")


@dataclass(frozen=True, slots=True)
class ScanRequest:
    repository: str
    revision: str
    includes: tuple[str, ...]
    excludes: tuple[str, ...] = ()
    roots: tuple[str, ...] = ()
    collectors: tuple[str, ...] = ("workflow",)
    budget: ScanBudget = field(default_factory=ScanBudget)

    def __post_init__(self) -> None:
        if not isinstance(self.repository, str) or not self.repository.strip():
            raise ValueError("repository is required")
        if not isinstance(self.revision, str) or not _HEX_SHA.fullmatch(self.revision):
            raise ValueError("revision must be an exact 40-character git SHA-1")
        object.__setattr__(self, "revision", self.revision.lower())
        for name in ("includes", "excludes", "roots", "collectors"):
            values = getattr(self, name)
            if not isinstance(values, tuple):
                raise ValueError(f"{name} must be a duplicate-free tuple")
            if name in ("includes", "excludes"):
                for value in values:
                    normalized_path(value, allow_pattern=True)
            else:
                for value in values:
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError(f"{name} values must be nonempty strings")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must be a duplicate-free tuple")
        if not self.includes:
            raise ValueError("includes must not be empty")
        if not self.collectors:
            raise ValueError("collectors must not be empty")
        if not isinstance(self.budget, ScanBudget):
            raise TypeError("budget must be a ScanBudget")

    def selects(self, path: str) -> bool:
        normalized_path(path)
        return any(fnmatchcase(path, p) for p in self.includes) and not any(
            fnmatchcase(path, p) for p in self.excludes
        )
