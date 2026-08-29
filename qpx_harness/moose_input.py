"""Reusable structure-aware MOOSE/HIT input block editing."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping


class MooseInputError(RuntimeError):
    pass


@dataclass(frozen=True)
class BlockSpan:
    path: str
    start: int
    end: int  # exclusive


_BLOCK_RE = re.compile(r"^\s*\[([^\]]*)\]\s*(?:#.*)?$")


class MooseInput:
    """Offset-preserving block view for standard MOOSE/HIT bracket syntax."""

    def __init__(self, text: str):
        self.text = text
        self.blocks = self._parse(text)

    @staticmethod
    def _parse(text: str) -> list[BlockSpan]:
        stack: list[tuple[str, int]] = []
        blocks: list[BlockSpan] = []
        offset = 0
        for line in text.splitlines(keepends=True):
            match = _BLOCK_RE.match(line.rstrip("\r\n"))
            if match:
                token = match.group(1).strip()
                if token in {"", "../"}:
                    if not stack:
                        raise MooseInputError(f"unmatched closing block at byte {offset}")
                    names = [name for name, _ in stack]
                    _, start = stack.pop()
                    blocks.append(BlockSpan("/".join(names), start, offset + len(line)))
                else:
                    if token.startswith("./"):
                        token = token[2:]
                    stack.append((token, offset))
            offset += len(line)

        if stack:
            raise MooseInputError(
                "unclosed MOOSE block(s): " + ", ".join(name for name, _ in stack)
            )
        return blocks

    def find(self, path: str) -> list[BlockSpan]:
        return [block for block in self.blocks if block.path == path]

    def unique(self, path: str) -> BlockSpan:
        matches = self.find(path)
        if len(matches) != 1:
            raise MooseInputError(f"expected one block {path!r}, found {len(matches)}")
        return matches[0]

    def remove_paths(self, paths: Iterable[str]) -> tuple[str, dict[str, list[int]]]:
        spans: list[BlockSpan] = []
        meta: dict[str, list[int]] = {}
        for path in paths:
            span = self.unique(path)
            spans.append(span)
            meta[path] = [span.start, span.end]

        ordered = sorted(spans, key=lambda span: span.start)
        for left, right in zip(ordered, ordered[1:]):
            if left.end > right.start:
                raise MooseInputError(
                    f"requested removal spans overlap: {left.path} and {right.path}"
                )

        result = self.text
        for span in sorted(spans, key=lambda item: item.start, reverse=True):
            result = result[: span.start] + result[span.end :]
        return result, meta

    def _parameter_matches(self, path: str, name: str) -> tuple[BlockSpan, str, list[re.Match[str]]]:
        span = self.unique(path)
        block_text = self.text[span.start : span.end]
        pattern = re.compile(
            rf"(?m)^(?P<prefix>\s*{re.escape(name)}\s*=\s*)"
            rf"(?P<value>[^#\r\n]*?)"
            rf"(?P<suffix>\s*(?:#.*)?$)"
        )
        return span, block_text, list(pattern.finditer(block_text))

    def replace_parameters(
        self, path: str, replacements: Mapping[str, str]
    ) -> tuple[str, dict[str, dict[str, str]]]:
        """Replace exactly one assignment per requested parameter inside one block."""
        span = self.unique(path)
        block_text = self.text[span.start : span.end]
        result = block_text
        meta: dict[str, dict[str, str]] = {}

        for name, new_value in replacements.items():
            pattern = re.compile(
                rf"(?m)^(?P<prefix>\s*{re.escape(name)}\s*=\s*)"
                rf"(?P<value>[^#\r\n]*?)"
                rf"(?P<suffix>\s*(?:#.*)?$)"
            )
            matches = list(pattern.finditer(result))
            if len(matches) != 1:
                raise MooseInputError(
                    f"expected one parameter {name!r} in block {path!r}, "
                    f"found {len(matches)}"
                )
            match = matches[0]
            old_value = match.group("value").strip()
            replacement = f"{match.group('prefix')}{new_value}{match.group('suffix')}"
            result = result[: match.start()] + replacement + result[match.end() :]
            meta[name] = {"old": old_value, "new": str(new_value)}

        transformed = self.text[: span.start] + result + self.text[span.end :]
        return transformed, meta

    def remove_parameters(
        self, path: str, names: Iterable[str]
    ) -> tuple[str, dict[str, str]]:
        """Remove exactly one line-oriented assignment per name inside one block."""
        span = self.unique(path)
        block_text = self.text[span.start : span.end]
        result = block_text
        meta: dict[str, str] = {}

        for name in names:
            pattern = re.compile(
                rf"(?m)^\s*{re.escape(name)}\s*=\s*(?P<value>[^#\r\n]*?)"
                rf"\s*(?:#.*)?(?:\r?\n|$)"
            )
            matches = list(pattern.finditer(result))
            if len(matches) != 1:
                raise MooseInputError(
                    f"expected one parameter {name!r} in block {path!r}, "
                    f"found {len(matches)}"
                )
            match = matches[0]
            meta[name] = match.group("value").strip()
            result = result[: match.start()] + result[match.end() :]

        transformed = self.text[: span.start] + result + self.text[span.end :]
        return transformed, meta

    def insert_before_close(self, path: str, fragment: str) -> tuple[str, int]:
        """Insert HIT text immediately before the unique block's closing line."""
        span = self.unique(path)
        block_text = self.text[span.start : span.end]
        stripped = block_text.rstrip("\r\n")
        close_line_start = stripped.rfind("\n") + 1
        close_line = stripped[close_line_start:].strip()
        if close_line not in {"[]", "[../]"}:
            raise MooseInputError(
                f"could not identify closing line for block {path!r}: {close_line!r}"
            )
        insert_at = span.start + close_line_start
        payload = fragment
        if payload and not payload.endswith("\n"):
            payload += "\n"
        transformed = self.text[:insert_at] + payload + self.text[insert_at:]
        return transformed, insert_at


def self_test() -> int:
    try:
        text = """# comment
[Variables]
  [u]
    type = FVReal
  []
  [phi]
    type = FVReal
  []
[]
[FVKernels]
  [flow]
    variable = u
  []
  [poisson]
    variable = phi
  []
[]
[Executioner]
  type = Transient
  dt = 1.0e-4
  end_time = 5.0e-4
  compute_scaling_once = false # retained comment
[]
"""
        doc = MooseInput(text)
        if doc.unique("Variables/phi").path != "Variables/phi":
            raise AssertionError("unique nested lookup failed")
        transformed, meta = doc.remove_paths(
            ("Variables/phi", "FVKernels/poisson")
        )
        if "[phi]" in transformed or "[poisson]" in transformed:
            raise AssertionError("block removal failed")
        if "[u]" not in transformed or "[flow]" not in transformed:
            raise AssertionError("unrelated block changed")
        if set(meta) != {"Variables/phi", "FVKernels/poisson"}:
            raise AssertionError("removal metadata mismatch")

        tuned, params = MooseInput(text).replace_parameters(
            "Executioner",
            {
                "dt": "1.0e-8",
                "end_time": "1.0e-8",
                "compute_scaling_once": "true",
            },
        )
        if "dt = 1.0e-8" not in tuned or "end_time = 1.0e-8" not in tuned:
            raise AssertionError("parameter replacement failed")
        if "compute_scaling_once = true # retained comment" not in tuned:
            raise AssertionError("parameter replacement did not preserve comment")
        if params["dt"] != {"old": "1.0e-4", "new": "1.0e-8"}:
            raise AssertionError("parameter replacement metadata mismatch")

        removed, removed_params = MooseInput(text).remove_parameters(
            "Executioner", ("dt", "end_time")
        )
        if "dt =" in MooseInput(removed).text[MooseInput(removed).unique("Executioner").start : MooseInput(removed).unique("Executioner").end]:
            raise AssertionError("parameter removal failed")
        if removed_params != {"dt": "1.0e-4", "end_time": "5.0e-4"}:
            raise AssertionError("parameter removal metadata mismatch")

        inserted, insert_at = MooseInput(text).insert_before_close(
            "Variables", "  [n_e]\n    type = FVReal\n  []"
        )
        variables = MooseInput(inserted)
        if variables.unique("Variables/n_e").start != insert_at:
            raise AssertionError("block insertion failed")
        if variables.unique("Variables/phi").path != "Variables/phi":
            raise AssertionError("block insertion changed existing structure")

        duplicate = text.replace(
            "  dt = 1.0e-4\n",
            "  dt = 1.0e-4\n  dt = 2.0e-4\n",
        )
        try:
            MooseInput(duplicate).replace_parameters("Executioner", {"dt": "1e-8"})
        except MooseInputError:
            pass
        else:
            raise AssertionError("duplicate parameter ambiguity was not rejected")
        try:
            MooseInput(duplicate).remove_parameters("Executioner", ("dt",))
        except MooseInputError:
            pass
        else:
            raise AssertionError("duplicate parameter removal ambiguity was not rejected")

        missing = text.replace("  end_time = 5.0e-4\n", "")
        try:
            MooseInput(missing).replace_parameters(
                "Executioner", {"end_time": "1e-8"}
            )
        except MooseInputError:
            pass
        else:
            raise AssertionError("missing parameter was not rejected")

        duplicate_block = text + """
[Variables]
  [phi]
  []
[]
"""
        try:
            MooseInput(duplicate_block).unique("Variables/phi")
        except MooseInputError:
            pass
        else:
            raise AssertionError("duplicate block ambiguity was not rejected")

        try:
            MooseInput("[Variables]\n  [u]\n[]\n")
        except MooseInputError:
            pass
        else:
            raise AssertionError("unclosed parent block was not rejected")
    except Exception as exc:
        print(f"MOOSE_INPUT_SELFTEST: FAIL ({exc})")
        return 1
    print("MOOSE_INPUT_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
