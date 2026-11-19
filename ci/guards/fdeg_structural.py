#!/usr/bin/env python3
"""FDEG Structural Evidence v0.3: read-only, source-bound consumer graph.

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
import time
import posixpath
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = "fdeg.structural.v0.3"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fdeg_structural_enrichment as route_evidence  # noqa: E402
import fdeg_scan_cache as scan_cache  # noqa: E402
EXTENSIONS = {".C", ".cc", ".cpp", ".h", ".hpp", ".py", ".i", ".json", ".yml", ".yaml", ".sh"}
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
MOOSE_ASSIGN = re.compile(r'^\s*([A-Za-z_][\w.-]*)\s*=\s*(.*?)\s*(?:#.*)?$')
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
        return ([root / p for p in sorted(set(names)) if p and (Path(p).suffix in EXTENSIONS or Path(p).name == "Makefile")
                 and not (set(Path(p).parts) & SKIP_DIRS)], git(root, "rev-parse", "HEAD"))
    return (sorted(p for p in root.rglob("*") if p.is_file() and (p.suffix in EXTENSIONS or p.name == "Makefile")
                   and not (set(p.relative_to(root).parts) & SKIP_DIRS)), None)


def tracked_blob_manifest(root: Path) -> dict[str, str]:
    """Complete tracked path/blob identities from the Git index, without file IO."""
    result = {}
    for row in git(root, "ls-files", "--stage", "-z").split("\0"):
        if not row:
            continue
        metadata, rel = row.split("\t", 1)
        fields = metadata.split()
        if len(fields) != 3 or fields[2] != "0":
            raise ValueError("FDEG_GIT_INDEX_NOT_NORMALIZED")
        path = Path(rel)
        if ((path.suffix in EXTENSIONS or path.name == "Makefile")
                and not (set(path.parts) & SKIP_DIRS)):
            result[rel] = fields[1]
    return result


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



def stable_id(prefix: str, payload: object) -> str:
    """Canonical IDs are content-addressed, not tied to traversal ordering."""
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return prefix + ":" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def input_blocks(text: str) -> list[dict]:
    """Collect declarative MOOSE input blocks and explicit bindings, not effective runtime values."""
    root = {"path": "", "open_line": 1, "bindings": []}
    frames = [root]
    blocks = [root]
    for line_no, raw in enumerate(text.splitlines(), 1):
        block = BLOCK.match(raw)
        if block:
            name = block.group(1).strip()
            if name in {"", "..", "../"}:
                if len(frames) > 1:
                    frames.pop()
            else:
                component = name[2:] if name.startswith("./") else name
                parent = frames[-1]["path"]
                context = {"path": parent + "/" + component if parent else component,
                           "open_line": line_no, "bindings": []}
                blocks.append(context)
                frames.append(context)
            continue
        match = MOOSE_ASSIGN.match(raw)
        if match and not raw.lstrip().startswith("#"):
            frames[-1]["bindings"].append(
                {"name": match.group(1), "raw_value": match.group(2).strip(),
                 "line": line_no})
    return blocks


def scan(root: Path, target: str, expected_head: str | None = None) -> dict:
    root = root.resolve()
    started = time.perf_counter()
    if not SYMBOL.fullmatch(target):
        raise ValueError("INVALID_CXX_CLASS_NAME")
    # Verify the HEAD and the tracked worktree *before* loading a cached graph.
    # A cached graph is strictly a performance shortcut for an earlier complete
    # source scan; caller-zero, runtime and retirement verdicts never change.
    git_head = git(root, "rev-parse", "HEAD") if (root / ".git").exists() else None
    if expected_head is not None and git_head != expected_head:
        raise ValueError("EXACT_HEAD_MISMATCH")
    cache = None
    if git_head is not None:
        dirty = bool(git(root, "status", "--porcelain", "--untracked-files=no"))
        if expected_head is not None and dirty:
            raise ValueError("TRACKED_WORKTREE_DIRTY")
        if not dirty:
            try:
                cache = scan_cache.cache_key(
                    root, git_head, target,
                    (Path(__file__), Path(route_evidence.__file__),
                     Path(scan_cache.__file__)))
            except OSError:
                cache = None
            if cache is not None:
                hit = scan_cache.load(cache, target, git_head, SCHEMA, stable_id)
                if hit is not None:
                    print("FDEG_STRUCTURAL_CACHE=HIT target=" + target +
                          " seconds=" + format(time.perf_counter() - started, ".3f"),
                          file=sys.stderr)
                    return hit
    implementation = (Path(__file__), Path(route_evidence.__file__),
                      Path(scan_cache.__file__))
    source_key = scan_cache.source_index_key(root, git_head, implementation) if cache else None
    source_payload = (scan_cache.load_source_index(
        source_key, tracked_blob_manifest(root)) if source_key else None)
    if source_payload is not None:
        # This is a complete HEAD-pinned set of tracked sources and scan errors,
        # not a target substring filter. Every target retains the same coverage.
        contents, errors = source_payload
        head = git_head
        print("FDEG_SOURCE_INDEX=HIT files=" + str(len(contents)), file=sys.stderr)
    else:
        files, head = tracked_files(root)
        if expected_head is not None and (head is None or head != expected_head):
            raise ValueError("EXACT_HEAD_MISMATCH")
        contents: dict[str, tuple[str, str]] = {}
        errors: list[dict] = []
        for path in files:
            rel = path.relative_to(root).as_posix()
            try:
                data = path.read_bytes()
                contents[rel] = (data.decode("utf-8"), blob_sha(data))
            except (OSError, UnicodeError) as exc:
                errors.append({"path": rel, "reason": type(exc).__name__})
        if source_key is not None:
            print("FDEG_SOURCE_INDEX=" + ("MISS_STORED" if
                  scan_cache.save_source_index(source_key, contents, errors)
                  else "MISS_UNSTORED") +
                  " files=" + str(len(contents)), file=sys.stderr)
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
    instances: list[dict] = []
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
                    if name not in aliases and ("$" in name or "{" in name):
                        unknown(path, i, "DYNAMIC_MOOSE_TYPE")
                m = MOOSE_INCLUDE.match(line)
                if m:
                    name = m.group(1)
                    dest = posixpath.normpath(posixpath.join(posixpath.dirname(path), name))
                    if dest in source_names:
                        emit(node, "INCLUDES_INPUT", "file:" + dest, path, i, name)
                    else:
                        unknown(path, i, "INCLUDE_UNRESOLVED:" + name)
            for context in input_blocks(text):
                bindings = context["bindings"]
                for assignment in bindings:
                    if assignment["name"] != "type":
                        continue
                    factory = assignment["raw_value"].strip("'\"")
                    if factory not in aliases:
                        continue
                    line_no = assignment["line"]
                    instance_id = "instance:" + stable_id(
                        "input", [path, context["path"], line_no, factory])
                    record = {
                        "instance_id": instance_id,
                        "input_path": path,
                        "block_path": context["path"],
                        "factory_type": factory,
                        "type_line": line_no,
                        "bindings": sorted(bindings, key=lambda b: (b["line"], b["name"])),
                        "evidence": {"path": path, "line": line_no,
                                     "blob_sha": contents[path][1]}
                    }
                    instances.append(record)
                    emit(node, "DECLARES_INSTANCE", instance_id, path, line_no,
                         "block=" + context["path"])
                    emit(instance_id, "INPUT_INSTANTIATES", class_id, path,
                         line_no, factory)
        elif suffix == ".py":
            try:
                tree = ast.parse(text, filename=path)
            except SyntaxError as exc:
                errors.append({"path": path, "line": exc.lineno, "reason": "PYTHON_PARSE_ERROR"})
                continue
            # Imported module is a static route, not execution.
            for n in ast.walk(tree):
                if isinstance(n, ast.ImportFrom) and n.module:
                    module_base = n.module.replace(".", "/")
                    candidates = [module_base + ".py"]
                    candidates.extend(module_base + "/" + alias.name + ".py"
                                      for alias in n.names if alias.name != "*")
                    for module in sorted(set(candidates)):
                        if module in source_names:
                            emit(node, "PYTHON_IMPORTS_MODULE", "file:" + module,
                                 path, n.lineno, n.module, "STATIC_IMPORT_NOT_EXECUTION")
                elif isinstance(n, ast.Import):
                    for alias in n.names:
                        module = alias.name.replace(".", "/") + ".py"
                        if module in source_names:
                            emit(node, "PYTHON_IMPORTS_MODULE", "file:" + module,
                                 path, n.lineno, alias.name, "STATIC_IMPORT_NOT_EXECUTION")
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
                    call_name = (n.func.attr if isinstance(n.func, ast.Attribute)
                                 else n.func.id if isinstance(n.func, ast.Name) else "")
                    moose_type_call = call_name in {
                        "upsert_parameter", "_insert_kernel", "add_kernel",
                        "add_fv_kernel", "addFVKernel", "addKernel",
                        "add_moose_object", "build_moose_object"}
                    for kw in n.keywords:
                        if kw.arg == "type" and moose_type_call:
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
            for candidate in route_evidence.python_template_instances(text, target, aliases):
                line_no = candidate["type_line"]
                instance_id = "instance:" + stable_id(
                    "input-template", [path, candidate["block_path"], line_no,
                                       candidate["factory_type"]])
                if instance_id in {item["instance_id"] for item in instances}:
                    continue
                instances.append({
                    "instance_id": instance_id,
                    "input_path": path, "block_path": candidate["block_path"],
                    "factory_type": candidate["factory_type"],
                    "type_line": line_no,
                    "bindings": sorted(candidate["bindings"], key=lambda b: (b["line"], b["name"])),
                    "instance_kind": candidate["source_kind"],
                    "runtime_activation": "NOT_OBSERVED",
                    "generated_output_path": "UNKNOWN",
                    "evidence": {"path": path, "line": line_no, "blob_sha": contents[path][1]},
                })
                emit(node, "PYTHON_DECLARES_TEMPLATE_INSTANCE", instance_id,
                     path, line_no, candidate["block_path"], "SOURCE_TEMPLATE_NOT_GENERATED")
                emit(instance_id, "PYTHON_TEMPLATE_INSTANTIATES", class_id,
                     path, line_no, candidate["factory_type"], "SOURCE_TEMPLATE_NOT_RUNTIME")
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

    # Independent source-line census. Missing mapped template blocks remain HOLD.
    template_declarations = []
    for source_path, (source_text, source_sha) in sorted(contents.items()):
        if not source_path.endswith(".py"):
            continue
        for source_line, raw in enumerate(source_text.splitlines(), 1):
            if re.match(r'^\s{2,}type\s*=\s*' + re.escape(target) + r'\s*$', raw):
                template_declarations.append({
                    "path": source_path, "line": source_line, "blob_sha": source_sha})
    mapped_declarations = {(item["input_path"], item["type_line"])
                           for item in instances
                           if item.get("instance_kind") ==
                           "PYTHON_GENERATED_INPUT_TEMPLATE_NOT_EXECUTED"}
    missing_template_declarations = [
        item for item in template_declarations
        if (item["path"], item["line"]) not in mapped_declarations]
    for item in missing_template_declarations:
        unknown(item["path"], item["line"],
                "PYTHON_TEMPLATE_TYPE_DECLARATION_NOT_MAPPED:" + target)

    # New v0.3 evidence is appended before reachability to include chained
    # provider and build declarations in the target-rooted graph.
    enrichment = route_evidence.enrichment(contents, target, aliases, instances,
                                          edges, emit, unknown)

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
    for edge in selected:
        path = edge["evidence"]["path"]
        edge["source_head"] = head
        edge["revision_scope"] = route_evidence.scope(path)
        edge["activation_status"] = "NOT_OBSERVED"
        edge["source_role"] = (
            "STATIC_TEMPLATE_CANDIDATE_NOT_RUNTIME"
            if edge["relation"] in {"PYTHON_TEMPLATE_INSTANTIATES",
                                   "PYTHON_DECLARES_TEMPLATE_INSTANCE"}
            else "SOURCE_RELATION_NOT_RUNTIME")
        if edge["relation"] == "MENTIONS_SYMBOL":
            source_line = edge["evidence"]["excerpt"]
            if re.search(r'\b(?:assert|forbidden|must.not|not.in)\b', source_line, re.I):
                edge["reference_role"] = "ASSERTION_OR_PROHIBITION_NOT_RUNTIME"
            else:
                edge["reference_role"] = "LEXICAL_REFERENCE_NOT_CONSUMER"
        elif edge["relation"] in {"GENERATOR_EMITS_OBJECT_CANDIDATE", "PYTHON_DECLARES_TYPE",
                                   "PYTHON_WRITES_INPUT", "PYTHON_TEMPLATE_INSTANTIATES",
                                   "PYTHON_DECLARES_TEMPLATE_INSTANCE"}:
            edge["reference_role"] = "STATIC_GENERATOR_NOT_RUNTIME"
        elif edge["relation"] in {"WORKFLOW_RUNS_SCRIPT", "WORKFLOW_CALLS", "SHELL_RUNS_SCRIPT",
                                   "PYTHON_IMPORTS_MODULE"}:
            edge["reference_role"] = "DECLARED_WORKFLOW_PATH_NOT_EXECUTION"
        elif edge["relation"] in {"PRODUCES_FUNCTOR_CANDIDATE", "BINDS_PARAMETER"}:
            edge["reference_role"] = "DECLARED_PROVIDER_OR_BINDING_NOT_EFFECTIVE"
        else:
            edge["reference_role"] = "STRUCTURAL_DECLARATION_NOT_RUNTIME"
        edge["edge_id"] = stable_id("edge", edge)
    instance_list = sorted(
        (item for item in instances if item["instance_id"] in reached),
        key=lambda item: item["instance_id"])
    edge_ids = {edge["from"]: edge["edge_id"] for edge in selected
                if edge["relation"] in {"INPUT_INSTANTIATES",
                                        "PYTHON_TEMPLATE_INSTANTIATES"}}
    for item in instance_list:
        item["structural_edge_id"] = edge_ids[item["instance_id"]]
    nodes = [{"id": item, "kind": "CLASS" if item.startswith("class:")
              else "INSTANCE" if item.startswith("instance:")
              else "FUNCTOR" if item.startswith("functor:") else "FILE"}
             for item in sorted(reached)]
    # A large workflow file is not a causal join for unrelated diagnostics.
    evidence_lines = {(e["evidence"]["path"], e["evidence"]["line"])
                      for e in selected}
    for item in instance_list:
        evidence_lines.update((item["input_path"], b["line"])
                              for b in item["bindings"])
    scoped_unresolved = [
        entry for entry in unresolved
        if (entry["path"], entry["line"]) in evidence_lines]
    generator_paths = {e["evidence"]["path"] for e in selected
                       if e["relation"] in {"GENERATOR_EMITS_OBJECT_CANDIDATE",
                                           "PYTHON_TEMPLATE_INSTANTIATES",
                                           "PYTHON_DECLARES_TYPE"}}
    target_input_paths = {item["input_path"] for item in instance_list
                          if item["input_path"].endswith(".i")}
    # Same-source unknown writes/includes can be upstream but not directly
    # mapped to the target node. Preserve them in a separate class rather
    # than hiding them or treating all workflow diagnostics as target blockers.
    upstream_unresolved = [
        entry for entry in unresolved
        if (entry["path"], entry["line"]) not in evidence_lines
        and ((entry["path"] in generator_paths
              and entry["reason"].startswith(("GENERATED_INPUT_NOT_TRACKED",
                                               "DYNAMIC_PYTHON_TYPE",
                                               "GENERATED_INPUT_NOT_TRACKED_OR_OBSERVED")))
             or (entry["path"] in target_input_paths
                 and entry["reason"].startswith("INCLUDE_UNRESOLVED")))]
    global_only_unresolved_count = (
        len(unresolved) - len(scoped_unresolved) - len(upstream_unresolved))
    global_status = "INCOMPLETE" if errors or unresolved else "STRUCTURAL_RECORDED"
    target_status = ("INCOMPLETE" if scoped_unresolved or upstream_unresolved
                     or missing_template_declarations
                     else "DECLARATIONS_ONLY_RUNTIME_UNVERIFIED")
    report = {"schema": SCHEMA, "target": target, "repository_head": head,
              "global_scan_status": global_status,
              "target_dependency_status": target_status,
              "global_unresolved_count": len(unresolved),
              "target_scoped_unresolved_count": len(scoped_unresolved),
              "upstream_unresolved_count": len(upstream_unresolved),
              "global_only_unresolved_count": global_only_unresolved_count,
              "unresolved_scope_semantics": {
                  "target": "SAME_SOURCE_WITNESS_LINE",
                  "upstream": "TARGET_GENERATOR_OR_DECLARED_INPUT_SOURCE_WITH_UNRESOLVED_DEPENDENCY",
                  "global": "NOT_CAUSALLY_JOINED_TO_TARGET"},
              "source_template_census": {
                  "declared_lines": template_declarations,
                  "mapped_virtual_instances": len(mapped_declarations),
                  "unmapped_declarations": missing_template_declarations,
                  "status": ("SOURCE_TEMPLATE_GAP" if missing_template_declarations
                             else "SOURCE_TEMPLATE_DECLARATIONS_MAPPED_NOT_EXECUTED"),
                  "runtime_coverage": "NOT_PROVEN",
                  "external_consumer_coverage": "NOT_PROVEN"},
              "scan_scope": {"tracked_only": head is not None, "extensions": sorted(EXTENSIONS),
                             "files_scanned": len(contents),
                             "untracked_generated_inputs_included": head is None},
              "nodes": nodes, "edges": selected, "instances": instance_list,
              "enrichment": enrichment,
              "target_scoped_unresolved": sorted(scoped_unresolved, key=lambda x: (x["path"], x["line"], x["reason"])),
              "upstream_unresolved": sorted(upstream_unresolved, key=lambda x: (x["path"], x["line"], x["reason"])),
              "unresolved": sorted(unresolved, key=lambda x: (x["path"], x["line"], x["reason"])),
              "scan_errors": errors,
              "status": "INCOMPLETE" if errors or unresolved else "STRUCTURAL_RECORDED",
              "safety": "NO_CALLER_ZERO_OR_RETIREMENT_VERDICT"}
    report["graph_id"] = stable_id("graph", report)
    if cache is not None:
        saved = scan_cache.save(cache, report)
        print("FDEG_STRUCTURAL_CACHE=" + ("MISS_STORED" if saved else "MISS_UNSTORED") +
              " target=" + target +
              " seconds=" + format(time.perf_counter() - started, ".3f"),
              file=sys.stderr)
    return report


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
