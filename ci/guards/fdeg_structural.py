#!/usr/bin/env python3
"""FDEG Structural Evidence v0.1: read-only, source-bound consumer graph.

This scanner records syntactic relations, not runtime use, semantic equivalence,
caller-zero, or permission to retire an object. Every emitted relationship is
attributed to source bytes and a line. Unresolved dynamic inputs stay explicit.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import posixpath
import re
import subprocess
from pathlib import Path

SCHEMA = "fdeg.structural.v0.1"
EXTENSIONS = {".C", ".cc", ".cpp", ".h", ".hpp", ".py", ".i", ".json", ".yml", ".yaml"}
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
REGISTRATION = re.compile(
    r'\bregister(?:AD)?MooseObject(Aliased)?\s*\(\s*"([^"\n]+)"\s*,\s*([A-Za-z_]\w*)\s*(?:,\s*"([^"\n]+)")?\s*\)'
)
DECLARATION = re.compile(r'\bclass\s+([A-Za-z_]\w*)\b')
ACTION_REGISTRATION = re.compile(
    r'\bregisterMooseAction\s*\(\s*"([^"\n]+)"\s*,\s*([A-Za-z_]\w*)\s*,\s*"([^"\n]+)"\s*\)'
)
ACTION_SYNTAX = re.compile(
    r'\b(?:registerSyntax|registerActionSyntax)\s*\(\s*"([^"\n]+)"\s*,\s*"([^"\n]+)"\s*\)'
)
BASE_TASKS = re.compile(r'\bregisterPhysicsBaseTasks\s*\(\s*"([^"\n]+)"\s*,\s*([A-Za-z_]\w*)\s*\)')
BLOCK = re.compile(r'^\s*\[([^\[\]]*)\]')
TYPE_BINDING = re.compile(r'\b(?:const\s+)?(?:auto|std::string|MooseObjectName)\s+([A-Za-z_]\w*)\s*=\s*"([^"\n]+)"')
CXX_CREATE_VAR = re.compile(
    r'\b(?:addFVKernel|addKernel|addFVBC|addBoundaryCondition|addMaterial|addUserObject|addAuxKernel|addMooseObject)\s*\(\s*([A-Za-z_]\w*)\s*[,)]'
)
CXX_CREATE = re.compile(
    r'\b(?:addFVKernel|addKernel|addFVBC|addBoundaryCondition|addMaterial|addUserObject|addAuxKernel|addMooseObject)\s*\(\s*"([^"\n]+)"'
)
CXX_NEW = re.compile(r'\b(?:new\s+|make_unique\s*<\s*|make_shared\s*<\s*)([A-Za-z_]\w*)')
MOOSE_TYPE = re.compile(r'^\s*type\s*=\s*(.*?)\s*(?:#.*)?$')
MOOSE_INCLUDE = re.compile(r'^\s*!include\s+["\']?([^"\'\s#]+)')
WORKFLOW_SCRIPT = re.compile(r'\b(?:python3?|bash|sh)\s+(?!-)([A-Za-z0-9_./-]+\.(?:py|sh))\b')
WORKFLOW_USES = re.compile(r'\buses:\s*(\./[^\s#]+\.ya?ml)\b')
CPP_INCLUDE = re.compile(r'^\s*#\s*include\s+"([^"\n]+)"')
SYMBOL = re.compile(r'[A-Za-z_]\w*')


def git(root: Path, *args: str) -> str:
    cmd = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    if cmd.returncode:
        raise ValueError("GIT_IDENTITY_UNAVAILABLE: " + cmd.stderr.strip())
    return cmd.stdout.strip()


def tracked_files(root: Path) -> tuple[list[Path], str | None]:
    if (root / ".git").exists():
        names = git(root, "ls-files", "-z").split("\0")
        return ([root / p for p in sorted(set(names)) if p and Path(p).suffix in EXTENSIONS
                 and not (set(Path(p).parts) & SKIP_DIRS)], git(root, "rev-parse", "HEAD"))
    return (sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in EXTENSIONS
                   and not (set(p.relative_to(root).parts) & SKIP_DIRS)), None)


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) and all(isinstance(v, ast.Constant) for v in node.values):
        return "".join(str(v.value) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        lhs, rhs = literal(node.left), literal(node.right)
        if lhs is not None and rhs is not None:
            return lhs + rhs
    return None


def python_output_path(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "Path" and len(node.args) == 1):
        return literal(node.args[0])
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left, right = python_output_path(node.left), literal(node.right)
        if left is not None and right is not None:
            return posixpath.join(left, right)
    return None


def scan(root: Path, target: str, expected_head: str | None = None) -> dict:
    root = root.resolve()
    if not SYMBOL.fullmatch(target):
        raise ValueError("INVALID_CXX_CLASS_NAME")
    files, head = tracked_files(root)
    if expected_head is not None and (head is None or head != expected_head):
        raise ValueError("EXACT_HEAD_MISMATCH")
    if expected_head is not None and git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("TRACKED_WORKTREE_DIRTY")
    contents: dict[str, tuple[str, str]] = {}
    errors: list[dict] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            data = path.read_bytes()
            contents[rel] = (data.decode("utf-8"), blob_sha(data))
        except (OSError, UnicodeError) as exc:
            errors.append({"path": rel, "reason": type(exc).__name__})
    aliases = {target}
    for text, _ in contents.values():
        for match in REGISTRATION.finditer(text):
            if match.group(3) == target and match.group(1) and match.group(4):
                aliases.add(match.group(4))
    action_syntax: set[str] = set()
    for text, _ in contents.values():
        for match in ACTION_SYNTAX.finditer(text):
            if match.group(1) == target:
                action_syntax.add(match.group(2))
    edges: list[dict] = []
    unresolved: list[dict] = []
    class_id = "class:" + target
    source_names = set(contents)

    def emit(source: str, relation: str, destination: str, path: str, line: int,
             detail: str, strength: str = "DIRECT_STATIC") -> None:
        text, sha = contents[path]
        excerpt = text.splitlines()[line - 1].strip()[:240] if 0 < line <= len(text.splitlines()) else ""
        edges.append({"from": source, "relation": relation, "to": destination,
                      "strength": strength, "detail": detail,
                      "evidence": {"path": path, "line": line, "blob_sha": sha, "excerpt": excerpt}})

    def unknown(path: str, line: int, reason: str) -> None:
        unresolved.append({"path": path, "line": line, "reason": reason,
                           "blob_sha": contents[path][1]})

    for path, (text, _) in contents.items():
        node = "file:" + path
        suffix = Path(path).suffix
        if suffix in {".C", ".cc", ".cpp", ".h", ".hpp"}:
            for match in REGISTRATION.finditer(text):
                if match.group(3) == target:
                    emit(node, "REGISTERS", class_id, path, line_of(text, match.start()),
                         "app=" + match.group(2) + ";factory=" + (match.group(4) or target))
            for match in ACTION_REGISTRATION.finditer(text):
                if match.group(2) == target:
                    emit(node, "REGISTERS_ACTION", class_id, path, line_of(text, match.start()),
                         "app=" + match.group(1) + ";task=" + match.group(3))
            for match in BASE_TASKS.finditer(text):
                if match.group(2) == target:
                    emit(node, "REGISTERS_PHYSICS_TASKS", class_id, path,
                         line_of(text, match.start()), match.group(1))
            for match in ACTION_SYNTAX.finditer(text):
                if match.group(1) == target:
                    emit(node, "REGISTERS_ACTION_SYNTAX", class_id, path,
                         line_of(text, match.start()), match.group(2))
            for match in DECLARATION.finditer(text):
                if match.group(1) == target:
                    emit(node, "DECLARES", class_id, path, line_of(text, match.start()), target)
            for match in CXX_CREATE.finditer(text):
                if match.group(1) in aliases:
                    emit(node, "ACTION_CREATES", class_id, path, line_of(text, match.start()), match.group(1))
            bindings = [(m.start(), m.group(1), m.group(2)) for m in TYPE_BINDING.finditer(text)
                        if m.group(2) in aliases]
            for match in CXX_CREATE_VAR.finditer(text):
                prior = [(position, name) for position, name, _ in bindings
                         if name == match.group(1) and position < match.start()]
                if prior:
                    emit(node, "ACTION_CREATES_VIA_LOCAL_LITERAL", class_id, path,
                         line_of(text, match.start()), "variable=" + match.group(1),
                         "LEXICAL_FLOW_CANDIDATE")
            for match in CXX_NEW.finditer(text):
                if match.group(1) == target:
                    emit(node, "CPP_CONSTRUCTS", class_id, path, line_of(text, match.start()), target)
            for i, line in enumerate(text.splitlines(), 1):
                inc = CPP_INCLUDE.match(line)
                if inc and inc.group(1).split("/")[-1] == target + ".h":
                    emit(node, "INCLUDES_TARGET_HEADER", class_id, path, i, inc.group(1))
                if re.search(r"\b" + re.escape(target) + r"\b", line):
                    emit(node, "MENTIONS_SYMBOL", class_id, path, i, target, "LEXICAL_ONLY")
        elif suffix == ".i":
            stack: list[str] = []
            for i, line in enumerate(text.splitlines(), 1):
                block = BLOCK.match(line)
                if block:
                    name = block.group(1).strip()
                    if name in {"", "..", "../"}:
                        if stack:
                            stack.pop()
                    elif name.startswith("./"):
                        stack.append(name[2:])
                    else:
                        stack.append(name)
                    current = "/".join(stack)
                    for syntax in sorted(action_syntax):
                        if fnmatch.fnmatchcase(current, syntax):
                            emit(node, "INPUT_MATCHES_ACTION_SYNTAX", class_id, path, i,
                                 "input=" + current + ";syntax=" + syntax, "DECLARED_INPUT_ONLY")
                m = MOOSE_TYPE.match(line)
                if m:
                    name = m.group(1).strip().strip("'\"")
                    if name in aliases:
                        emit(node, "INPUT_INSTANTIATES", class_id, path, i, name)
                    elif "$" in name or "{" in name:
                        unknown(path, i, "DYNAMIC_MOOSE_TYPE")
                m = MOOSE_INCLUDE.match(line)
                if m:
                    name = m.group(1)
                    dest = posixpath.normpath(posixpath.join(posixpath.dirname(path), name))
                    if dest in source_names:
                        emit(node, "INCLUDES_INPUT", "file:" + dest, path, i, name)
                    else:
                        unknown(path, i, "INCLUDE_UNRESOLVED:" + name)
        elif suffix == ".py":
            try:
                tree = ast.parse(text, filename=path)
            except SyntaxError as exc:
                errors.append({"path": path, "line": exc.lineno, "reason": "PYTHON_PARSE_ERROR"})
                continue
            for n in ast.walk(tree):
                if isinstance(n, ast.Dict):
                    for key, value in zip(n.keys, n.values):
                        if key is not None and literal(key) in {"type", "object_type", "kernel_type"}:
                            name = literal(value)
                            if name in aliases:
                                emit(node, "PYTHON_DECLARES_TYPE", class_id, path, key.lineno, name)
                            elif name is None:
                                unknown(path, n.lineno, "DYNAMIC_PYTHON_TYPE")
                if isinstance(n, ast.Call):
                    for kw in n.keywords:
                        if kw.arg == "type":
                            name = literal(kw.value)
                            if name in aliases:
                                emit(node, "PYTHON_DECLARES_TYPE", class_id, path, n.lineno, name)
                            elif name is None:
                                unknown(path, n.lineno, "DYNAMIC_PYTHON_TYPE")
                    output = None
                    if isinstance(n.func, ast.Attribute) and n.func.attr in {"write_text", "write_bytes"}:
                        output = python_output_path(n.func.value)
                    elif (isinstance(n.func, ast.Name) and n.func.id == "open"
                          and len(n.args) >= 2 and (literal(n.args[1]) or "").startswith(("w", "a", "x"))):
                        output = python_output_path(n.args[0])
                    if output is not None and output.endswith(".i"):
                        dest = posixpath.normpath(output.removeprefix("./"))
                        if dest in source_names:
                            emit(node, "PYTHON_WRITES_INPUT", "file:" + dest, path, n.lineno, dest)
                        else:
                            unknown(path, n.lineno, "GENERATED_INPUT_NOT_TRACKED:" + dest)
                if isinstance(n, ast.Constant) and isinstance(n.value, str):
                    if target in SYMBOL.findall(n.value):
                        emit(node, "MENTIONS_SYMBOL", class_id, path, n.lineno, target, "LEXICAL_ONLY")
        elif suffix == ".json":
            try:
                doc = json.loads(text)
            except json.JSONDecodeError as exc:
                errors.append({"path": path, "line": exc.lineno, "reason": "JSON_PARSE_ERROR"})
                continue
            for match in re.finditer(
                    r'"(type|object_type|kernel_type)"\s*:\s*("[^"\n]*"|[^,}\]\n]+)', text):
                key, token = match.group(1), match.group(2).strip()
                line = line_of(text, match.start())
                if token.startswith('"') and token.endswith('"') and token[1:-1] in aliases:
                    emit(node, "JSON_DECLARES_TYPE", class_id, path, line, key)
                elif not token.startswith('"') or "$" in token or "{" in token:
                    unknown(path, line, "DYNAMIC_JSON_TYPE:" + key)
        elif suffix in {".yml", ".yaml"} and (path.startswith(".github/workflows/") or path.startswith("ci/workflow_templates/")):
            for match in WORKFLOW_SCRIPT.finditer(text):
                script = match.group(1).removeprefix("./")
                if script in source_names:
                    emit(node, "WORKFLOW_RUNS_SCRIPT", "file:" + script, path,
                         line_of(text, match.start()), script)
                else:
                    unknown(path, line_of(text, match.start()), "WORKFLOW_SCRIPT_UNRESOLVED:" + script)
            for match in WORKFLOW_USES.finditer(text):
                other = match.group(1).removeprefix("./")
                if other in source_names:
                    emit(node, "WORKFLOW_CALLS", "file:" + other, path,
                         line_of(text, match.start()), other)
                else:
                    unknown(path, line_of(text, match.start()), "WORKFLOW_CALLEE_UNRESOLVED:" + other)

    # The graph contains only incoming paths that can reach the selected class.
    reached = {class_id}
    changed = True
    while changed:
        previous = len(reached)
        reached.update(e["from"] for e in edges if e["to"] in reached)
        changed = len(reached) != previous
    selected = [e for e in edges if e["from"] in reached and e["to"] in reached]
    selected.sort(key=lambda e: (e["from"], e["relation"], e["to"], e["evidence"]["path"],
                                 e["evidence"]["line"], e["detail"]))
    nodes = [{"id": item, "kind": "CLASS" if item.startswith("class:") else "FILE"}
             for item in sorted(reached)]
    return {"schema": SCHEMA, "target": target, "repository_head": head,
            "scan_scope": {"tracked_only": head is not None, "extensions": sorted(EXTENSIONS),
                           "files_scanned": len(contents), "untracked_generated_inputs_included": head is None},
            "nodes": nodes, "edges": selected,
            "unresolved": sorted(unresolved, key=lambda x: (x["path"], x["line"], x["reason"])),
            "scan_errors": errors,
            "status": "INCOMPLETE" if errors or unresolved else "STRUCTURAL_RECORDED",
            "safety": "NO_CALLER_ZERO_OR_RETIREMENT_VERDICT"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Exact C++ class name")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--expected-head", help="Require this exact Git HEAD and clean tracked worktree")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()
    try:
        result = scan(args.root, args.target, args.expected_head)
    except (ValueError, OSError) as exc:
        print("FDEG_STRUCTURAL_P0=FAIL: " + str(exc))
        return 1
    data = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(data, encoding="utf-8")
        print("FDEG_STRUCTURAL_REPORT=" + str(args.output))
    else:
        print(data, end="")
    print("FDEG_STRUCTURAL_P0=" + ("HOLD" if result["status"] == "INCOMPLETE" else "PASS"))
    return 2 if result["status"] == "INCOMPLETE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
