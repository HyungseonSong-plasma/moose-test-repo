"""Small dependency-free coercion helpers shared by analysis mapping owners."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def self_test() -> int:
    try:
        assert as_mapping({"a": 1}) == {"a": 1}
        assert as_mapping(None) == {}
        assert optional_float("1.25") == 1.25
        assert optional_float(True) is None
        assert optional_int("3.9") == 3
        assert optional_int(False) is None
        assert string_tuple(["u", 1, "v"]) == ("u", "v")
        assert string_tuple("uv") == ()
    except Exception as exc:
        print(f"QPX_ANALYSIS_COERCION_SELFTEST: FAIL ({exc})")
        return 1

    print("QPX_ANALYSIS_COERCION_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
