"""Shared offset-preserving C++ lexical masking; no Graph or domain dependencies."""

def mask_cpp(text: str, *, mask_literals: bool) -> str:
    """Preserve offsets/newlines with either existing C++ mask convention.

    The literal-mask mode recognizes raw strings; the comment-only mode keeps
    the collector's existing ordinary quote interpretation. Neither mode
    establishes that the input is well-formed C++.
    """
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
                if mask_literals:
                    out[i] = " "
                i += 1
                state = "string"
                continue
            if mask_literals and c == "R" and n == '"':
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
                if mask_literals:
                    out[i] = " "
                if i + 1 < len(text):
                    if mask_literals and text[i + 1] != "\n":
                        out[i + 1] = " "
                    i += 2
                else:
                    i += 1
                continue
            if mask_literals and c != "\n":
                out[i] = " "
            i += 1
            if c == quote:
                state = "code"
    return "".join(out)
