"""Reusable structural helpers for C++ call expressions."""

from __future__ import annotations

from dataclasses import dataclass

from .cpp_source import CppSource, CppSourceError, Span


class CppCallError(CppSourceError):
    pass


@dataclass(frozen=True)
class CallArguments:
    call: Span
    open_paren: int
    close_paren: int
    arguments: tuple[str, ...]


def _find_call_parens(cpp: CppSource, call: Span) -> tuple[int, int]:
    open_idx = cpp.masked.find("(", call.start, call.end)
    if open_idx < 0:
        raise CppCallError(f"call span contains no opening parenthesis: {call}")
    close_idx = cpp.match_forward(open_idx, "(", ")")
    if close_idx >= call.end:
        raise CppCallError(f"call closing parenthesis escapes span: {call}")
    return open_idx, close_idx


def split_call_arguments(cpp: CppSource, call: Span) -> CallArguments:
    """Split a structurally identified C++ call at top-level commas.

    Comments and literals are already masked by ``CppSource``. Parentheses,
    brackets and braces are tracked structurally so nested function calls,
    indexing and initializer lists do not split the outer argument list.
    Angle brackets are tracked conservatively for template-id argument lists.
    """
    open_idx, close_idx = _find_call_parens(cpp, call)
    masked = cpp.masked
    text = cpp.text

    args: list[str] = []
    start = open_idx + 1
    paren = bracket = brace = angle = 0
    i = start
    while i < close_idx:
        c = masked[i]
        if c == "(":
            paren += 1
        elif c == ")":
            if paren == 0:
                raise CppCallError("unexpected ')' inside call argument list")
            paren -= 1
        elif c == "[":
            bracket += 1
        elif c == "]":
            if bracket == 0:
                raise CppCallError("unexpected ']' inside call argument list")
            bracket -= 1
        elif c == "{":
            brace += 1
        elif c == "}":
            if brace == 0:
                raise CppCallError("unexpected '}' inside call argument list")
            brace -= 1
        elif c == "<":
            # Conservative template-id heuristic: only count '<' when the
            # previous significant token looks like an identifier, '>' or ':'
            # and a matching '>' is reachable before the outer call closes.
            j = i - 1
            while j >= start and masked[j].isspace():
                j -= 1
            prev = masked[j] if j >= start else ""
            if prev.isalnum() or prev in "_>:":
                try:
                    match = cpp.match_forward(i, "<", ">")
                except CppSourceError:
                    match = -1
                if 0 <= match < close_idx:
                    angle += 1
        elif c == ">" and angle > 0:
            angle -= 1
        elif c == "," and paren == bracket == brace == angle == 0:
            args.append(text[start:i].strip())
            start = i + 1
        i += 1

    tail = text[start:close_idx].strip()
    if tail or args:
        args.append(tail)
    if any(not arg for arg in args):
        raise CppCallError(f"empty argument detected in call {call}")
    return CallArguments(call, open_idx, close_idx, tuple(args))


def self_test() -> int:
    try:
        source = r'''
void f()
{
  auto x = evaluateDmix(
      i,
      temperature(r, state),
      helper(foo(1, 2), bar(3)),
      values[j + 1],
      make_vec({1, 2, 3}),
      templated<Pair<A, B>>(q));
}
'''
        cpp = CppSource(source)
        call = cpp.unique_call("evaluateDmix")
        parsed = split_call_arguments(cpp, call)
        expected = (
            "i",
            "temperature(r, state)",
            "helper(foo(1, 2), bar(3))",
            "values[j + 1]",
            "make_vec({1, 2, 3})",
            "templated<Pair<A, B>>(q)",
        )
        if parsed.arguments != expected:
            raise AssertionError((parsed.arguments, expected))

        empty = CppSource("void f(){ auto x = evaluateDmix(); }")
        if split_call_arguments(empty, empty.unique_call("evaluateDmix")).arguments != ():
            raise AssertionError("empty call argument parsing failed")
    except Exception as exc:
        print(f"CPP_CALLS_SELFTEST: FAIL ({exc})")
        return 1
    print("CPP_CALLS_SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
