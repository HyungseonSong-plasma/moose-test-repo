"""Reusable QPX/MOOSE static preflight checks."""

from __future__ import annotations

import re
from pathlib import Path


TEMPORAL_RAW_POLICIES = {
    "include_initial_as_physics",
    "not_applicable_no_temporal_csv",
}

RESERVED_SYMBOLS = {"x", "y", "z", "t", "pi", "e"}
PARSED_FUNCTOR_TYPES = {"ParsedFunctorMaterial", "ADParsedFunctorMaterial"}
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BLOCK_OPEN_RE = re.compile(r"^\s*\[(?!\]|\.\./)(?:\./)?([^\]]+)\]\s*$")
BLOCK_CLOSE_RE = re.compile(r"^\s*\[(?:\.\./)?\]\s*$")
TYPE_RE = re.compile(r"^\s*type\s*=\s*([^\s#]+)", re.MULTILINE)
PARAM_RE_TEMPLATE = r"^\s*{name}\s*=\s*(?:'([^']*)'|\"([^\"]*)\"|([^#\n]+))"


def _value_from_match(match: re.Match[str]) -> str:
    for group in match.groups():
        if group is not None:
            return group.strip()
    return ""


def _extract_param(block_text: str, name: str) -> list[str] | None:
    pattern = re.compile(PARAM_RE_TEMPLATE.format(name=re.escape(name)), re.MULTILINE)
    match = pattern.search(block_text)
    if not match:
        return None
    return _value_from_match(match).split()


def _parsed_blocks(text: str) -> list[tuple[str, str]]:
    """Return (block_path, block_text) for leaf-style MOOSE input blocks."""

    stack: list[str] = []
    starts: list[int] = []
    blocks: list[tuple[str, str]] = []
    lines = text.splitlines()

    for index, line in enumerate(lines):
        open_match = BLOCK_OPEN_RE.match(line)
        if open_match:
            stack.append(open_match.group(1).strip())
            starts.append(index)
            continue

        if BLOCK_CLOSE_RE.match(line) and stack:
            start = starts.pop()
            path = "/".join(stack)
            blocks.append((path, "\n".join(lines[start : index + 1])))
            stack.pop()

    while stack:
        start = starts.pop()
        path = "/".join(stack)
        blocks.append((path, "\n".join(lines[start:])))
        stack.pop()

    return blocks


def validate_parser_symbols_text(text: str, source: str = "<memory>") -> list[str]:
    errors: list[str] = []

    for block_path, block_text in _parsed_blocks(text):
        type_match = TYPE_RE.search(block_text)
        if not type_match:
            continue

        object_type = type_match.group(1).strip()
        if object_type not in PARSED_FUNCTOR_TYPES:
            continue

        symbols = _extract_param(block_text, "functor_symbols")
        source_param = "functor_symbols"
        if symbols is None:
            symbols = _extract_param(block_text, "functor_names") or []
            source_param = "functor_names (used as parser symbols because functor_symbols is omitted)"

        if not symbols:
            continue

        duplicates = sorted({symbol for symbol in symbols if symbols.count(symbol) > 1})
        if duplicates:
            errors.append(
                f"{source}:{block_path}: duplicate parser symbols in {source_param}: "
                + ", ".join(duplicates)
            )

        reserved = sorted(RESERVED_SYMBOLS.intersection(symbols))
        if reserved:
            errors.append(
                f"{source}:{block_path}: reserved parser symbol collision in {source_param}: "
                + ", ".join(reserved)
                + "; ParsedFunctorMaterial/ADParsedFunctorMaterial reserve x,y,z,t and pi,e"
            )

        invalid = sorted({symbol for symbol in symbols if not IDENTIFIER_RE.match(symbol)})
        if invalid:
            errors.append(
                f"{source}:{block_path}: invalid parser identifiers in {source_param}: "
                + ", ".join(invalid)
            )

    return errors


def validate_parser_symbols_file(path: Path) -> list[str]:
    try:
        text = path.read_text()
    except UnicodeDecodeError as exc:
        return [f"{path}: cannot decode input as UTF-8: {exc}"]
    return validate_parser_symbols_text(text, str(path))


# Compatibility aliases used by the historical CLI/module API.
validate_text = validate_parser_symbols_text
validate_file = validate_parser_symbols_file


def validate_input_preflight(input_path: Path) -> None:
    if not input_path.is_file():
        raise SystemExit(f"missing test input: {input_path}")

    errors = validate_parser_symbols_file(input_path)
    if errors:
        print("PARSER_P0  : FAIL")
        for error in errors:
            print("  -", error)
        raise SystemExit(2)

    print("PARSER_P0  : PASS")


def is_transient_input(input_path: Path) -> bool:
    return bool(
        re.search(r"^\s*type\s*=\s*Transient\b", input_path.read_text(), re.MULTILINE)
    )


def validate_temporal_manifest_preflight(input_path: Path, cfg: dict) -> None:
    """Require explicit temporal-row semantics for schema-v2 transient cases."""

    checker = cfg.get("checker")
    if not checker or not is_transient_input(input_path):
        return

    schema = int(cfg.get("validation_schema", 1))
    if schema < 2:
        print("TEMPORAL_P0: LEGACY_SCHEMA_WARNING")
        return

    specs = cfg.get("temporal_csv", [])
    raw_policy = cfg.get("temporal_csv_policy")

    if not specs and raw_policy not in TEMPORAL_RAW_POLICIES:
        print("TEMPORAL_P0: FAIL")
        raise SystemExit(
            "validation_schema=2 transient test with checker must declare either "
            "test.json temporal_csv normalization or an explicit temporal_csv_policy; "
            "silent initialization-row semantics are forbidden"
        )

    if raw_policy is not None and raw_policy not in TEMPORAL_RAW_POLICIES:
        print("TEMPORAL_P0: FAIL")
        raise SystemExit(
            f"unsupported temporal_csv_policy={raw_policy!r}; "
            f"expected one of {sorted(TEMPORAL_RAW_POLICIES)}"
        )

    checker_args = [str(value) for value in cfg.get("checker_args", [])]
    for spec in specs:
        for key in ("source", "physical", "initial_row_policy"):
            if key not in spec:
                print("TEMPORAL_P0: FAIL")
                raise SystemExit(f"temporal_csv entry missing required key {key!r}")

        source = str(spec["source"])
        physical = str(spec["physical"])
        if source == physical:
            print("TEMPORAL_P0: FAIL")
            raise SystemExit(
                "temporal_csv source and physical paths must differ; raw runtime evidence "
                "must be preserved"
            )

        if source in checker_args and spec["initial_row_policy"] == "exclude_observation":
            print("TEMPORAL_P0: FAIL")
            raise SystemExit(
                f"checker_args references raw temporal CSV {source!r}; use normalized "
                f"physical CSV {physical!r} instead"
            )

        csv_args = [arg for arg in checker_args if arg.lower().endswith(".csv")]
        if csv_args and physical not in csv_args:
            print("TEMPORAL_P0: FAIL")
            raise SystemExit(
                f"checker_args contains CSV paths {csv_args} but not normalized temporal "
                f"CSV {physical!r}"
            )

    print("TEMPORAL_P0: PASS")


def parser_symbol_self_test() -> int:
    safe = """
[FunctorMaterials]
  [rho_w]
    type = ADParsedFunctorMaterial
    functor_names = 'rho w_O'
    functor_symbols = 'fp_rho fp_w'
    expression = 'fp_rho*fp_w'
    property_name = rho_w
  []
[]
"""
    bad_reserved = """
[FunctorMaterials]
  [rho_w]
    type = ADParsedFunctorMaterial
    functor_names = 'rho w_O'
    functor_symbols = 'r y'
    expression = 'r*y'
    property_name = rho_w
  []
[]
"""
    bad_implicit = """
[FunctorMaterials]
  [coord_like]
    type = ParsedFunctorMaterial
    functor_names = 'rho x'
    expression = 'rho*x'
    property_name = p
  []
[]
"""
    bad_duplicate = """
[FunctorMaterials]
  [dup]
    type = ADParsedFunctorMaterial
    functor_names = 'rho w_O'
    functor_symbols = 'fp_a fp_a'
    expression = 'fp_a*fp_a'
    property_name = q
  []
[]
"""

    checks = [
        ("safe aliases", not validate_parser_symbols_text(safe)),
        (
            "reserved explicit y",
            any(
                "reserved parser symbol collision" in error
                for error in validate_parser_symbols_text(bad_reserved)
            ),
        ),
        (
            "reserved implicit x",
            any(
                "reserved parser symbol collision" in error
                for error in validate_parser_symbols_text(bad_implicit)
            ),
        ),
        (
            "duplicate alias",
            any(
                "duplicate parser symbols" in error
                for error in validate_parser_symbols_text(bad_duplicate)
            ),
        ),
    ]

    failed = [name for name, ok in checks if not ok]
    if failed:
        print("PARSER_SYMBOL_PREFLIGHT_SELFTEST: FAIL")
        for name in failed:
            print("  -", name)
        return 1

    print("PARSER_SYMBOL_PREFLIGHT_SELFTEST: PASS")
    return 0
