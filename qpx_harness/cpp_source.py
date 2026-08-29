"""Reusable structure-aware C++ source scanner for QPX harness source edits.

This is deliberately smaller than a full C++ parser. Regex is used only to
locate lexical anchors; comments/strings are masked and structural boundaries
are resolved with balanced delimiters so nested calls/lambdas do not truncate
source spans.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


class CppSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Span:
    start: int
    end: int  # exclusive

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError(f"invalid span [{self.start}, {self.end})")

    def contains(self, pos: int) -> bool:
        return self.start <= pos < self.end

    def slice(self, text: str) -> str:
        return text[self.start : self.end]


class CppSource:
    """Offset-preserving structural view of one C++ translation unit."""

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
        if right is None:
            raise CppSourceError(f"unsupported delimiter {left!r}")
        if self.masked[open_idx] != left:
            raise CppSourceError(f"expected {left!r} at index {open_idx}")
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

    def function_body(self, signature: str) -> Span:
        """Return the brace span for exactly one function-definition signature anchor."""
        hits = [m.start() for m in re.finditer(re.escape(signature), self.masked)]
        bodies: list[Span] = []
        for idx in hits:
            brace = self.masked.find("{", idx)
            semi = self.masked.find(";", idx)
            if brace < 0 or (semi >= 0 and semi < brace):
                continue
            bodies.append(Span(brace, self.match_forward(brace, "{", "}") + 1))
        if len(bodies) != 1:
            raise CppSourceError(
                f"expected one function body for {signature!r}, found {len(bodies)} "
                f"(signature_hits={len(hits)})"
            )
        return bodies[0]

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
            raise CppSourceError(f"unbalanced opening brace(s): {stack[-5:]}")
        return spans

    def _header_keyword(self, block: Span) -> str | None:
        brace_idx = block.start
        i = brace_idx - 1
        while i >= 0 and self.masked[i].isspace():
            i -= 1
        if i < 0 or self.masked[i] != ")":
            return None
        open_paren = self.match_backward(i, "(", ")")
        j = open_paren - 1
        while j >= 0 and self.masked[j].isspace():
            j -= 1
        end = j + 1
        while j >= 0 and (self.masked[j].isalnum() or self.masked[j] == "_"):
            j -= 1
        return self.masked[j + 1 : end] or None

    def enclosing_blocks(self, anchor_pattern: str, *, keyword: str | None = None) -> list[Span]:
        matches = list(re.finditer(anchor_pattern, self.masked, re.MULTILINE))
        if len(matches) != 1:
            raise CppSourceError(
                f"expected one anchor for {anchor_pattern!r}, found {len(matches)}"
            )
        pos = matches[0].start()
        spans = [span for span in self.block_spans() if span.start < pos < span.end]
        if keyword is not None:
            spans = [span for span in spans if self._header_keyword(span) == keyword]
        spans.sort(key=lambda span: span.end - span.start)
        return spans

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
        if pos < limit and self.masked[pos] == "(":
            return pos
        return None

    def calls(self, callee: str, *, containing: str | None = None, within: Span | None = None) -> list[Span]:
        """Find balanced call-expression spans for a final identifier name."""
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
            if containing is not None and containing not in self.masked[span.start : span.end]:
                continue
            spans.append(span)
        return spans

    def unique_call(self, callee: str, *, containing: str | None = None, within: Span | None = None) -> Span:
        spans = self.calls(callee, containing=containing, within=within)
        if len(spans) != 1:
            raise CppSourceError(
                f"expected one call {callee!r}"
                + (f" containing {containing!r}" if containing else "")
                + f", found {len(spans)}"
            )
        return spans[0]

    def lambda_body(self, call: Span) -> Span:
        """Return the first actual lambda body structurally contained in a call.

        Array subscripts such as ``_D_mix_names[i]`` are rejected because the
        first non-whitespace token after ``]`` is not a lambda declarator/body.
        """
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
            if pos < call.end and self.masked[pos] == "<":
                try:
                    pos = self.match_forward(pos, "<", ">") + 1
                except CppSourceError:
                    search = capture_end + 1
                    continue
                pos = self._skip_ws(pos, call.end)

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
        """Return complete `return [this->]callee(...);` statement spans."""
        lo = within.start if within else 0
        hi = within.end if within else len(self.masked)
        pattern = re.compile(
            rf"\breturn\s+(?:this\s*->\s*)?{re.escape(callee)}\s*\("
        )
        spans: list[Span] = []
        for match in pattern.finditer(self.masked, lo, hi):
            open_idx = self.masked.find("(", match.start(), match.end())
            if open_idx < 0:
                continue
            close_idx = self.match_forward(open_idx, "(", ")")
            pos = self._skip_ws(close_idx + 1, hi)
            if pos >= hi or self.masked[pos] != ";":
                continue
            spans.append(Span(match.start(), pos + 1))
        return spans

    def unique_return_call(self, callee: str, *, within: Span | None = None) -> Span:
        spans = self.return_calls(callee, within=within)
        if len(spans) != 1:
            raise CppSourceError(
                f"expected one return call {callee!r}, found {len(spans)}"
            )
        return spans[0]

    def replace(self, span: Span, replacement: str) -> str:
        return self.text[: span.start] + replacement + self.text[span.end :]


def mask_cpp(text: str) -> str:
    """Mask comments and quoted literals while preserving source offsets/newlines."""
    out = list(text)
    i = 0
    state = "code"
    quote = ""
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""
        if state == "code":
            if c == "R" and n == '"':
                paren = text.find("(", i + 2, min(len(text), i + 20))
                if paren >= 0:
                    delim = text[i + 2 : paren]
                    if (
                        len(delim) <= 16
                        and not any(ch.isspace() or ch in "\\()" for ch in delim)
                    ):
                        closer = ")" + delim + '"'
                        close = text.find(closer, paren + 1)
                        end = len(text) if close < 0 else close + len(closer)
                        for k in range(i, end):
                            if text[k] != "\n":
                                out[k] = " "
                        i = end
                        continue
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
            i += 1
            continue
        if state == "line_comment":
            if c == "\n":
                state = "code"
            else:
                out[i] = " "
            i += 1
            continue
        if state == "block_comment":
            if c == "*" and n == "/":
                out[i] = out[i + 1] = " "
                i += 2
                state = "code"
            else:
                if c != "\n":
                    out[i] = " "
                i += 1
            continue
        if state == "string":
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


def self_test() -> int:
    try:
        source = r'''// fake addFunctorProperty<ADReal>(_D_mix_names[i], [] { return evaluateDmix(bad); });
const char * fake = "return evaluateDmix(fake); { [ (";
const char * raw = R"tag(addFunctorProperty<ADReal>(_D_mix_names[i], []{ return evaluateDmix(raw); }); { [ ()tag";
/* fake loop: for (;;) { nDij[i][j] = 0; } */

void Owner::configure()
{
  this->addFunctorProperty<ADReal>(
      _D_mix_names[i],
      other_values[j],
      [this, i](const auto & r, const auto & state)
      {
        return evaluateDmix(
            i,
            _temperature(r, state),
            helper(foo(1, 2), bar(3)));
      });
}

Result
Owner::evaluate(const int & r, const int & state) const
{
  for (int i = 0; i < 7; ++i)
  {
    for (int j = 0; j < 7; ++j)
    {
      nDij[i][j] = i + j;
    }
  }
  return {};
}
'''
        cpp = CppSource(source)
        cpp.require_tokens(["_D_mix_names", "Owner::evaluate"])
        call = cpp.unique_call("addFunctorProperty", containing="_D_mix_names")
        body = cpp.lambda_body(call)
        ret = cpp.unique_return_call("evaluateDmix", within=body)
        if "helper(foo(1, 2), bar(3))" not in ret.slice(source):
            raise AssertionError("nested call span truncated")
        replacement = cpp.replace(ret, "return evaluate(r, state).D_mix[i];")
        if replacement.count("return evaluate(r, state).D_mix[i];") != 1:
            raise AssertionError("return replacement failed")

        function = cpp.function_body("Owner::evaluate")
        if "nDij[i][j]" not in function.slice(source):
            raise AssertionError("function body mismatch")
        loops = cpp.enclosing_blocks(
            r"nDij\s*\[\s*i\s*\]\s*\[\s*j\s*\]\s*=", keyword="for"
        )
        if len(loops) != 2:
            raise AssertionError(f"expected two enclosing loops, got {len(loops)}")

        duplicate = source.replace(
            "void Owner::configure()",
            "void Owner::configure2(){ addFunctorProperty<ADReal>(_D_mix_names[i], [] { return evaluateDmix(i); }); }\nvoid Owner::configure()",
        )
        try:
            CppSource(duplicate).unique_call("addFunctorProperty", containing="_D_mix_names")
        except CppSourceError:
            pass
        else:
            raise AssertionError("ambiguous call was not rejected")
    except Exception as exc:
        print(f"CPP_SOURCE_SELFTEST: FAIL ({exc})")
        return 1
    print("CPP_SOURCE_SELFTEST: PASS")
    return 0
