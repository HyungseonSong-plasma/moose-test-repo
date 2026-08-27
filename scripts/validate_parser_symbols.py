#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path


# ParsedFunctorMaterial/ADParsedFunctorMaterial append x,y,z,t internally and
# also register pi/e as parser constants. Generated test inputs must not reuse
# these names as user functor symbols.
RESERVED_SYMBOLS = {"x", "y", "z", "t", "pi", "e"}
PARSED_FUNCTOR_TYPES = {"ParsedFunctorMaterial", "ADParsedFunctorMaterial"}
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BLOCK_OPEN_RE = re.compile(r"^\s*\[(?!\]|\.\./)(?:\./)?([^\]]+)\]\s*$")
BLOCK_CLOSE_RE = re.compile(r"^\s*\[(?:\.\./)?\]\s*$")
TYPE_RE = re.compile(r"^\s*type\s*=\s*([^\s#]+)")
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
    value = _value_from_match(match)
    return value.split()


def _parsed_blocks(text: str) -> list[tuple[str, str]]:
    """Return (block_path, block_text) for leaf-style MOOSE input blocks.

    This intentionally implements only the bracket structure needed for static
    preflight. It does not attempt to evaluate substitutions or include files.
    """
    stack: list[str] = []
    starts: list[int] = []
    blocks: list[tuple[str, str]] = []
    lines = text.splitlines()

    for i, line in enumerate(lines):
        open_match = BLOCK_OPEN_RE.match(line)
        if open_match:
            stack.append(open_match.group(1).strip())
            starts.append(i)
            continue

        if BLOCK_CLOSE_RE.match(line) and stack:
            start = starts.pop()
            path = "/".join(stack)
            block_text = "\n".join(lines[start : i + 1])
            blocks.append((path, block_text))
            stack.pop()

    # Tolerate an unclosed final block so the static checker can still report
    # symbol defects instead of silently skipping it.
    while stack:
        start = starts.pop()
        path = "/".join(stack)
        blocks.append((path, "\n".join(lines[start:])))
        stack.pop()

    return blocks


def validate_text(text: str, source: str = "<memory>") -> list[str]:
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

        duplicates = sorted({s for s in symbols if symbols.count(s) > 1})
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

        invalid = sorted({s for s in symbols if not IDENTIFIER_RE.match(s)})
        if invalid:
            errors.append(
                f"{source}:{block_path}: invalid parser identifiers in {source_param}: "
                + ", ".join(invalid)
            )

    return errors


def validate_file(path: Path) -> list[str]:
    try:
        text = path.read_text()
    except UnicodeDecodeError as exc:
        return [f"{path}: cannot decode input as UTF-8: {exc}"]
    return validate_text(text, str(path))


def _self_test() -> int:
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
        ("safe aliases", not validate_text(safe)),
        ("reserved explicit y", any("reserved parser symbol collision" in e for e in validate_text(bad_reserved))),
        ("reserved implicit x", any("reserved parser symbol collision" in e for e in validate_text(bad_implicit))),
        ("duplicate alias", any("duplicate parser symbols" in e for e in validate_text(bad_duplicate))),
    ]

    failed = [name for name, ok in checks if not ok]
    if failed:
        print("PARSER_SYMBOL_PREFLIGHT_SELFTEST: FAIL")
        for name in failed:
            print("  -", name)
        return 1

    print("PARSER_SYMBOL_PREFLIGHT_SELFTEST: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reject ParsedFunctorMaterial parser-symbol collisions before qpx-opt."
    )
    parser.add_argument("paths", nargs="*", help="MOOSE input files to scan")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    if not args.paths:
        parser.error("provide at least one input path or --self-test")

    errors: list[str] = []
    for raw in args.paths:
        path = Path(raw)
        if not path.is_file():
            errors.append(f"{path}: file not found")
            continue
        errors.extend(validate_file(path))

    if errors:
        print("PARSER_SYMBOL_PREFLIGHT: FAIL")
        for error in errors:
            print("  -", error)
        return 2

    print("PARSER_SYMBOL_PREFLIGHT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
