"""Generic C++ source observation helpers.

C++ is a source language, not a semantic owner.  These utilities perform only
source-faithful structural inspection and contain no MOOSE scientific meaning.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


class CppSourceError(RuntimeError):
    pass


class CppCallError(CppSourceError):
    pass


@dataclass(frozen=True)
class Span:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"invalid span [{self.start}, {self.end})")

    def contains(self, pos: int) -> bool:
        return self.start <= pos < self.end

    def slice(self, text: str) -> str:
        return text[self.start:self.end]


@dataclass(frozen=True)
class CallArguments:
    call: Span
    open_paren: int
    close_paren: int
    arguments: tuple[str, ...]


def mask_cpp(text: str) -> str:
    """Mask comments and quoted literals while preserving offsets/newlines."""
    out = list(text)
    i = 0
    state = "code"
    quote = ""
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if state == "code":
            if c == "/" and n == "/":
                out[i] = out[i + 1] = " "
                i += 2
                state = "line_comment"
                continue
            if c == "/" and n == "*":
                out[i] = out[i + 1] = " "
                i += 2
                state = "block_comment"
                continue
            if c in {'"', "'"}:
                quote = c
                out[i] = " "
                i += 1
                state = "string"
                continue
            if c == "R" and n == '"':
                paren = text.find("(", i + 2, min(len(text), i + 20))
                if paren >= 0:
                    delim = text[i + 2:paren]
                    if len(delim) <= 16 and not any(ch.isspace() or ch in "\\()" for ch in delim):
                        closer = ")" + delim + '"'
                        close = text.find(closer, paren + 1)
                        end = len(text) if close < 0 else close + len(closer)
                        for k in range(i, end):
                            if text[k] != "\n":
                                out[k] = " "
                        i = end
                        continue
            i += 1
        elif state == "line_comment":
            if c == "\n":
                state = "code"
            else:
                out[i] = " "
            i += 1
        elif state == "block_comment":
            if c == "*" and n == "/":
                out[i] = out[i + 1] = " "
                i += 2
                state = "code"
            else:
                if c != "\n":
                    out[i] = " "
                i += 1
        else:
            if c == "\\":
                out[i] = " "
                if i + 1 < len(text):
                    if text[i + 1] != "\n":
                        out[i + 1] = " "
                    i += 2
                else:
                    i += 1
                continue
            if c != "\n":
                out[i] = " "
            i += 1
            if c == quote:
                state = "code"
    return "".join(out)


class CppSource:
    _PAIRS = {"(": ")", "{": "}", "[": "]", "<": ">"}

    def __init__(self, text: str):
        self.text = text
        self.masked = mask_cpp(text)

    def require_tokens(self, tokens: Iterable[str]) -> None:
        missing = [token for token in tokens if token not in self.masked]
        if missing:
            raise CppSourceError("missing source contract token(s): " + ", ".join(missing))

    def match_forward(self, open_idx: int, left: str | None = None, right: str | None = None) -> int:
        if open_idx < 0 or open_idx >= len(self.masked):
            raise CppSourceError(f"opening index out of range: {open_idx}")
        left = left or self.masked[open_idx]
        right = right or self._PAIRS.get(left)
        if right is None or self.masked[open_idx] != left:
            raise CppSourceError(f"invalid delimiter at {open_idx}")
        depth = 0
        for i in range(open_idx, len(self.masked)):
            c = self.masked[i]
            if c == left:
                depth += 1
            elif c == right:
                depth -= 1
                if depth == 0:
                    return i
        raise CppSourceError(f"unmatched {left!r} at index {open_idx}")

    def match_backward(self, close_idx: int, left: str, right: str) -> int:
        if close_idx < 0 or close_idx >= len(self.masked) or self.masked[close_idx] != right:
            raise CppSourceError(f"expected {right!r} at index {close_idx}")
        depth = 0
        for i in range(close_idx, -1, -1):
            c = self.masked[i]
            if c == right:
                depth += 1
            elif c == left:
                depth -= 1
                if depth == 0:
                    return i
        raise CppSourceError(f"unmatched {right!r} at index {close_idx}")

    def block_spans(self) -> list[Span]:
        stack: list[int] = []
        spans: list[Span] = []
        for i, c in enumerate(self.masked):
            if c == "{":
                stack.append(i)
            elif c == "}":
                if not stack:
                    raise CppSourceError(f"unbalanced closing brace at {i}")
                spans.append(Span(stack.pop(), i + 1))
        if stack:
            raise CppSourceError("unbalanced opening brace")
        return spans

    def _block_is_control_body(self, span: Span, keyword: str) -> bool:
        """Return whether ``span`` is the braced body of ``keyword (...)``."""
        pos = span.start - 1
        while pos >= 0 and self.masked[pos].isspace():
            pos -= 1
        if pos < 0 or self.masked[pos] != ")":
            return False
        try:
            open_paren = self.match_backward(pos, "(", ")")
        except CppSourceError:
            return False
        pos = open_paren - 1
        while pos >= 0 and self.masked[pos].isspace():
            pos -= 1
        end = pos + 1
        while pos >= 0 and (self.masked[pos].isalnum() or self.masked[pos] == "_"):
            pos -= 1
        return self.masked[pos + 1:end] == keyword

    def enclosing_blocks(self, pattern: str, *, keyword: str | None = None) -> list[Span]:
        """Return blocks enclosing source matches, from innermost to outermost.

        ``pattern`` is matched against masked source so comments and literals do
        not create false anchors. When ``keyword`` is supplied, only braced
        control bodies whose header has that keyword are returned; this is used
        by instrumentation code to identify nested ``for`` loop bodies without
        assigning any domain semantics to the source observer.
        """
        matches = list(re.finditer(pattern, self.masked))
        if not matches:
            raise CppSourceError(f"source pattern not found: {pattern!r}")
        candidates: set[Span] = set()
        blocks = self.block_spans()
        for match in matches:
            for span in blocks:
                if not span.contains(match.start()):
                    continue
                if keyword is not None and not self._block_is_control_body(span, keyword):
                    continue
                candidates.add(span)
        return sorted(candidates, key=lambda span: (span.end - span.start, span.start))

    def function_body(self, signature: str) -> Span:
        hits = [m.start() for m in re.finditer(re.escape(signature), self.masked)]
        bodies: list[Span] = []
        for idx in hits:
            brace = self.masked.find("{", idx)
            semi = self.masked.find(";", idx)
            if brace < 0 or (semi >= 0 and semi < brace):
                continue
            bodies.append(Span(brace, self.match_forward(brace, "{", "}") + 1))
        if len(bodies) != 1:
            raise CppSourceError(f"expected one function body for {signature!r}, found {len(bodies)}")
        return bodies[0]

    def _skip_ws(self, pos: int, limit: int | None = None) -> int:
        limit = len(self.masked) if limit is None else min(limit, len(self.masked))
        while pos < limit and self.masked[pos].isspace():
            pos += 1
        return pos

    def _call_open_after_name(self, name_end: int, limit: int | None = None) -> int | None:
        limit = len(self.masked) if limit is None else min(limit, len(self.masked))
        pos = self._skip_ws(name_end, limit)
        if pos < limit and self.masked[pos] == "<":
            try:
                pos = self.match_forward(pos, "<", ">") + 1
            except CppSourceError:
                return None
            pos = self._skip_ws(pos, limit)
        return pos if pos < limit and self.masked[pos] == "(" else None

    def calls(self, callee: str, *, containing: str | None = None, within: Span | None = None) -> list[Span]:
        lo = within.start if within else 0
        hi = within.end if within else len(self.masked)
        pattern = re.compile(rf"\b{re.escape(callee)}\b")
        spans: list[Span] = []
        for match in pattern.finditer(self.masked, lo, hi):
            open_idx = self._call_open_after_name(match.end(), hi)
            if open_idx is None:
                continue
            try:
                close_idx = self.match_forward(open_idx, "(", ")")
            except CppSourceError:
                continue
            if close_idx >= hi:
                continue
            span = Span(match.start(), close_idx + 1)
            if containing is not None and containing not in self.masked[span.start:span.end]:
                continue
            spans.append(span)
        return spans

    def unique_call(self, callee: str, *, containing: str | None = None, within: Span | None = None) -> Span:
        spans = self.calls(callee, containing=containing, within=within)
        if len(spans) != 1:
            raise CppSourceError(f"expected one call {callee!r}, found {len(spans)}")
        return spans[0]

    def lambda_body(self, call: Span) -> Span:
        search = call.start
        while True:
            capture = self.masked.find("[", search, call.end)
            if capture < 0:
                break
            try:
                capture_end = self.match_forward(capture, "[", "]")
            except CppSourceError:
                search = capture + 1
                continue
            pos = self._skip_ws(capture_end + 1, call.end)
            if pos < call.end and self.masked[pos] == "(":
                try:
                    pos = self.match_forward(pos, "(", ")") + 1
                except CppSourceError:
                    search = capture_end + 1
                    continue
                pos = self._skip_ws(pos, call.end)
            elif pos < call.end and self.masked[pos] != "{":
                search = capture_end + 1
                continue
            brace = self.masked.find("{", pos, call.end)
            if brace >= 0:
                close = self.match_forward(brace, "{", "}")
                if close < call.end:
                    return Span(brace, close + 1)
            search = capture_end + 1
        raise CppSourceError(f"no lambda body found inside call span {call}")

    def return_calls(self, callee: str, *, within: Span | None = None) -> list[Span]:
        lo = within.start if within else 0
        hi = within.end if within else len(self.masked)
        pattern = re.compile(rf"\breturn\s+(?:this\s*->\s*)?{re.escape(callee)}\s*\(")
        result: list[Span] = []
        for match in pattern.finditer(self.masked, lo, hi):
            open_idx = self.masked.find("(", match.start(), match.end())
            close_idx = self.match_forward(open_idx, "(", ")")
            pos = self._skip_ws(close_idx + 1, hi)
            if pos < hi and self.masked[pos] == ";":
                result.append(Span(match.start(), pos + 1))
        return result

    def unique_return_call(self, callee: str, *, within: Span | None = None) -> Span:
        spans = self.return_calls(callee, within=within)
        if len(spans) != 1:
            raise CppSourceError(f"expected one return call {callee!r}, found {len(spans)}")
        return spans[0]

    def replace(self, span: Span, replacement: str) -> str:
        return self.text[:span.start] + replacement + self.text[span.end:]


def split_call_arguments(cpp: CppSource, call: Span) -> CallArguments:
    open_idx = cpp.masked.find("(", call.start, call.end)
    if open_idx < 0:
        raise CppCallError("call span contains no opening parenthesis")
    close_idx = cpp.match_forward(open_idx, "(", ")")
    if close_idx >= call.end:
        raise CppCallError("call closing parenthesis escapes span")
    args: list[str] = []
    start = open_idx + 1
    paren = bracket = brace = angle = 0
    i = start
    while i < close_idx:
        c = cpp.masked[i]
        if c == "(":
            paren += 1
        elif c == ")":
            paren -= 1
        elif c == "[":
            bracket += 1
        elif c == "]":
            bracket -= 1
        elif c == "{":
            brace += 1
        elif c == "}":
            brace -= 1
        elif c == "<":
            angle += 1
        elif c == ">" and angle > 0:
            angle -= 1
        elif c == "," and paren == bracket == brace == angle == 0:
            args.append(cpp.text[start:i].strip())
            start = i + 1
        i += 1
    tail = cpp.text[start:close_idx].strip()
    if tail or args:
        args.append(tail)
    if any(not item for item in args):
        raise CppCallError("empty argument detected")
    return CallArguments(call, open_idx, close_idx, tuple(args))


__all__ = [
    "CallArguments", "CppCallError", "CppSource", "CppSourceError", "Span",
    "mask_cpp", "split_call_arguments",
]
