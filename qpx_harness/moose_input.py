"""Reusable structure-aware MOOSE/HIT input block editing."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


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

        duplicate = text + """
[Variables]
  [phi]
  []
[]
"""
        try:
            MooseInput(duplicate).unique("Variables/phi")
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
