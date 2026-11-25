"""Reusable CLI routing and JSON serialization; no domain dependencies."""
from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
import json
import math
from pathlib import Path
import subprocess
import sys


@dataclass(frozen=True, slots=True)
class Command:
    help: str
    configure: Callable[[argparse.ArgumentParser], None]
    execute: Callable[[argparse.Namespace], int]


def json_value(value):
    """Convert JSON-shaped records without silently coercing unknown objects."""
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: json_value(getattr(value, field.name))
                for field in fields(value)}
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("JSON mapping keys must be strings")
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((json_value(item) for item in value),
                      key=lambda item: json.dumps(item, sort_keys=True,
                                                  allow_nan=False))
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def write_json(value, path: Path | None = None) -> None:
    """Serialize before opening; existing evidence is never overwritten."""
    text = json.dumps(json_value(value), indent=2, sort_keys=True,
                      ensure_ascii=False, allow_nan=False) + "\n"
    if path is None:
        sys.stdout.write(text)
    else:
        with Path(path).open("x", encoding="utf-8") as stream:
            stream.write(text)


def dispatch(prog: str, commands: Mapping[str, Command],
             argv: Sequence[str] | None = None) -> int:
    """Dispatch one named handler. Domain handlers define result semantics."""
    parser = argparse.ArgumentParser(prog=prog, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, command in sorted(commands.items()):
        child = subparsers.add_parser(name, help=command.help,
                                      description=command.help,
                                      allow_abbrev=False)
        command.configure(child)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        result = commands[args.command].execute(args)
        if type(result) is not int or not 0 <= result <= 255:
            raise TypeError("Command handler must return an integer exit code")
        return result
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
        print(f"{prog}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
