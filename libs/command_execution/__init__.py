"""Domain-independent command dispatch and strict JSON output."""
from .cli import Command, dispatch, json_value, write_json

__all__ = ["Command", "dispatch", "json_value", "write_json"]
