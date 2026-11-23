"""FDEG v0.3 structural enrichment: source-bound routes, not executed consumers.

A static candidate may explain what a generator/provider *could* produce, but
is never evidence that an input or functor was produced at runtime.
"""
from __future__ import annotations

import ast
import posixpath
import re
import shlex

REG = re.compile(r'\bregister(?:AD)?MooseObject(?:Aliased)?\s*\(\s*"([^"]+)"\s*,\s*([A-Za-z_]\w*)')
INC = re.compile(r'^\s*#\s*include\s+"([^"]+)"')
BLOCK = re.compile(r'^\s*\[([^\[\]]*)\]')
ASSIGN = re.compile(r'^\s*([A-Za-z_][\w.-]*)\s*=\s*(.*?)\s*(?:#.*)?$')
RUN = re.compile(r'\b(?:python3?|bash|sh)\s+([A-Za-z0-9_./-]+\.(?:py|sh))\b')
FUNCTOR_PARAMS = {
    "temperature", "potential", "mobility", "diffusion", "carrier", "rho",
    "number_source", "thermal_diffusion_coefficient", "coeff",
    "electron_density", "anchor", "beta", "matrix",
    "electron_temperature", "electron_number_density"
}
PRODUCER_KEYS = {"prop_names", "property_name", "functor_name", "functor_names",
                 "D_T_names", "D_mix_names", "kT_names", "property_names"}
TOKEN = re.compile(r'[A-Za-z_]\w*')


def scope(path: str) -> str:
    if "/historical_" in path or path.startswith("archive/"):
        # Directory prefix is LOCATION evidence, not accepted lifecycle or execution.
        return "HISTORICAL_LOCATION_ACTIVITY_UNKNOWN"
    if path.startswith("tests/") or path.startswith("physics_app/ci/"):
        return "TEST_OR_CHECKER_ONLY"
    if path.startswith(".github/workflows/") or path.startswith("physics_harness/workflow/definitions/"):
        return "WORKFLOW_DECLARATION"
    return "CURRENT_SOURCE_NOT_PROVEN_ACTIVE"


def witness(contents: dict, path: str, line: int) -> dict:
    body, sha = contents[path]
    lines = body.splitlines()
    return {"path": path, "line": line, "blob_sha": sha,
            "excerpt": lines[line - 1].strip()[:240] if 0 < line <= len(lines) else ""}


def blocks(text: str) -> list[dict]:
    frames = [{"block_path": "", "bindings": [], "type": None}]
    found = []
    for line, raw in enumerate(text.splitlines(), 1):
        m = BLOCK.match(raw)
        if m:
            name = m.group(1).strip()
            if name in {"", "..", "../"}:
                if len(frames) > 1:
                    found.append(frames.pop())
            else:
                name = name.removeprefix("./")
                parent = frames[-1]["block_path"]
                frames.append({"block_path": (parent + "/" if parent else "") + name,
                               "bindings": [], "type": None})
            continue
        a = ASSIGN.match(raw)
        if a:
            binding = {"name": a.group(1), "value": a.group(2).strip(), "line": line}
            frames[-1]["bindings"].append(binding)
            if a.group(1) == "type":
                frames[-1]["type"] = a.group(2).strip("'\"")
    found.extend(frames[1:])
    return found


def tokens(value: str) -> list[str]:
    try:
        return [x for x in shlex.split(value) if TOKEN.fullmatch(x)]
    except ValueError:
        return []


def declared_providers(contents: dict) -> list[dict]:
    providers = []
    for path, (text, _) in sorted(contents.items()):
        if not path.endswith(".i"):
            continue
        for block in blocks(text):
            if not block["block_path"].startswith(("FunctorMaterials/", "Materials/")):
                continue
            ptype = block["type"] or ""
            if "Material" not in ptype:
                continue
            bindings = {item["name"]: item for item in block["bindings"]}
            for binding in block["bindings"]:
                if binding["name"] not in PRODUCER_KEYS:
                    continue
                for name in tokens(binding["value"]):
                    providers.append({"name": name, "path": path,
                                      "block_path": block["block_path"],
                                      "object_type": ptype, "kind": "DECLARED_PROPERTY_NAME",
                                      "evidence": witness(contents, path, binding["line"])})
            if ptype == "NVTransportMaterial" and "D_T_names" not in bindings:
                species = bindings.get("species_names")
                if species:
                    for name in tokens(species["value"]):
                        providers.append({"name": "D_T_" + name, "path": path,
                                          "block_path": block["block_path"],
                                          "object_type": ptype,
                                          "kind": "NVTRANSPORT_DEFAULT_NAMING_CANDIDATE",
                                          "evidence": witness(contents, path, species["line"])})
    return sorted(providers, key=lambda x: (x["name"], x["path"], x["block_path"]))


def _ast_ancestors(node: ast.AST, parents: dict):
    parent = parents.get(node)
    while parent is not None:
        yield parent
        parent = parents.get(parent)


def python_template_instances(text: str, target: str, aliases: set[str]) -> list[dict]:
    """Literal MOOSE [FVKernels] blocks inside Python strings: DECLARED only."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    parents = {child: parent for parent in ast.walk(tree)
               for child in ast.iter_child_nodes(parent)}
    results = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Constant, ast.JoinedStr)):
            continue
        if isinstance(parents.get(node), ast.JoinedStr):
            continue
        raw = ast.get_source_segment(text, node)
        if not raw or "[FVKernels]" not in raw or not re.search(r'\btype\s*=', raw):
            continue
        if any(isinstance(parent, (ast.Assert, ast.Compare))
               for parent in _ast_ancestors(node, parents)):
            continue
        lines = raw.splitlines()
        inside, block = False, None
        for i, line in enumerate(lines):
            cleaned = line.strip()
            if cleaned == "[FVKernels]" or cleaned.endswith('"""[FVKernels]') or cleaned.endswith("'''[FVKernels]"):
                inside, block = True, None
                continue
            if not inside:
                continue
            if cleaned.startswith("[") and cleaned.endswith("]"):
                name = cleaned.strip("[]").strip()
                if not name:
                    block = None
                elif name != "FVKernels":
                    # MOOSE templates may indent blocks by one or more spaces.
                    block = name if line[:1].isspace() else None
                    if block is None:
                        inside = False
                continue
            match = re.match(r'^\s*type\s*=\s*([A-Za-z_]\w*)\s*$', line)
            if not match or match.group(1) not in aliases or block is None:
                continue
            line_no = node.lineno + i
            bindings = [{"name": "type", "raw_value": match.group(1), "line": line_no}]
            for j in range(i + 1, len(lines)):
                other = lines[j]
                if other.strip().startswith("["):
                    break
                assignment = ASSIGN.match(other)
                if assignment and assignment.group(1) in {
                        "variable", "rho", "state_form", "number_source",
                        "potential", "temperature", "mobility", "diffusion",
                        "thermal_diffusion_coefficient", "carrier"}:
                    bindings.append({"name": assignment.group(1),
                                     "raw_value": assignment.group(2).strip(),
                                     "line": node.lineno + j})
            results.append({
                "factory_type": match.group(1),
                "block_path": "FVKernels/" + block,
                "type_line": line_no,
                "bindings": bindings,
                "source_kind": "PYTHON_GENERATED_INPUT_TEMPLATE_NOT_EXECUTED",
            })
    return sorted(results, key=lambda x: (x["type_line"], x["block_path"]))


def python_routes(contents: dict, target: str, aliases: set[str]) -> list[dict]:
    routes = []
    for path, (text, _) in sorted(contents.items()):
        if not path.endswith(".py"):
            continue
        if not any(name in text for name in aliases):
            continue
        try:
            tree = ast.parse(text, filename=path)
        except SyntaxError:
            continue  # Base scanner owns parse errors
        parents = {child: parent for parent in ast.walk(tree)
                   for child in ast.iter_child_nodes(parent)}
        taken = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.DictComp) and isinstance(node.value, ast.Constant):
                if node.value.value in aliases:
                    line = node.value.lineno
                    routes.append({"source": path, "line": line,
                                   "factory_type": node.value.value,
                                   "block_path_expression": ast.unparse(node.key)[:180],
                                   "route_kind": "STATIC_COMPREHENSION_TYPE_MAP",
                                   "generated_input_path": "UNKNOWN",
                                   "activation": "NOT_OBSERVED",
                                   "reference_scope": scope(path),
                                   "source_role": "STATIC_SOURCE_NOT_LIFECYCLE",
                                   "evidence": witness(contents, path, line)})
                    taken.add((node.value.lineno, node.value.col_offset))
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if not isinstance(value, ast.Constant) or value.value not in aliases:
                        continue
                    line = value.lineno
                    pattern = ast.unparse(key)[:180] if key is not None else "UNKNOWN"
                    routes.append({"source": path, "line": line,
                                   "factory_type": value.value, "block_path_expression": pattern,
                                   "route_kind": "STATIC_TYPE_MAP",
                                   "generated_input_path": "UNKNOWN",
                                   "activation": "NOT_OBSERVED",
                                   "reference_scope": scope(path),
                                   "source_role": "STATIC_SOURCE_NOT_LIFECYCLE",
                                   "evidence": witness(contents, path, line)})
                    taken.add((value.lineno, value.col_offset))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if (node.lineno, node.col_offset) in taken:
                continue
            if not any(name in TOKEN.findall(node.value) for name in aliases):
                continue
            writer = None
            blocked = False
            for parent in _ast_ancestors(node, parents):
                if isinstance(parent, (ast.Assert, ast.Compare, ast.If, ast.While)):
                    blocked = True
                    break
                if isinstance(parent, ast.Call):
                    fn = parent.func
                    name = fn.attr if isinstance(fn, ast.Attribute) else (
                        fn.id if isinstance(fn, ast.Name) else "")
                    if name in {"write_text", "write_bytes", "_insert_kernel",
                                "upsert_parameter", "set_parameter"}:
                        writer = name
            if blocked or writer is None:
                continue  # No writer/dataflow proof; never a generator edge.
            routes.append({"source": path, "line": node.lineno,
                           "factory_type": target, "block_path_expression": "UNKNOWN",
                           "route_kind": "STATIC_WRITER_ARGUMENT_CANDIDATE",
                           "generated_input_path": "UNKNOWN",
                           "activation": "NOT_OBSERVED",
                           "reference_scope": scope(path),
                                   "source_role": "STATIC_SOURCE_NOT_LIFECYCLE",
                           "writer": writer,
                           "evidence": witness(contents, path, node.lineno)})
    return sorted(routes, key=lambda x: (x["source"], x["line"],
                                          x["route_kind"], x["block_path_expression"]))


def enrichment(contents: dict, target: str, aliases: set[str], instances: list[dict],
               edges: list[dict], emit, unknown) -> dict:
    """Append source-bound incoming edges before graph reachability is computed."""
    result = {"build_ownership": [], "shared_translation_units": [],
              "generator_routes": [], "provider_bindings": [],
              "workflow_execution_paths": [], "external_imports": []}
    source_names = set(contents)
    owners = {}
    for path, (text, _) in sorted(contents.items()):
        if path.endswith((".C", ".cc", ".cpp")):
            classes = [(m.group(2), text.count("\n", 0, m.start()) + 1)
                       for m in REG.finditer(text)]
            if any(name == target for name, _ in classes):
                owners[path] = classes

    for path, registered in sorted(owners.items()):
        all_classes = sorted({name for name, _ in registered})
        result["shared_translation_units"].append({
            "source_path": path, "blob_sha": contents[path][1],
            "registered_classes": all_classes,
            "status": "SOURCE_REGISTRATIONS_ONLY",
            "whole_file_retirement": "REQUIRES_ALL_REGISTERED_OWNERS_DISCONNECTED"})
        text = contents[path][0]
        for line, raw in enumerate(text.splitlines(), 1):
            inc = INC.match(raw)
            if not inc or inc.group(1).split("/")[-1].endswith((".h", ".hpp")) is False:
                continue
            matches = [name for name in sorted(source_names)
                       if name.endswith("/" + inc.group(1).split("/")[-1])
                       and name.endswith((".h", ".hpp"))]
            if len(matches) == 1 and re.search(r'\bclass\s+' + re.escape(target) + r'\b',
                                               contents[matches[0]][0]):
                emit("file:" + path, "INCLUDES_OWNER_HEADER", "file:" + matches[0],
                     path, line, inc.group(1), "SOURCE_INCLUDE_ONLY")
                declaration = re.search(r'\bclass\s+' + re.escape(target) + r'\b',
                                        contents[matches[0]][0])
                header_line = contents[matches[0]][0].count("\n", 0, declaration.start()) + 1
                emit("file:" + matches[0], "HEADER_DECLARES_TARGET", "class:" + target,
                     matches[0], header_line, target, "HEADER_SOURCE_ONLY")
            elif inc.group(1).split("/")[-1] in {target + ".h",
                   path.rsplit("/", 1)[-1].removesuffix(".C") + ".h"}:
                unknown(path, line, "TARGET_HEADER_OWNER_UNRESOLVED:" + inc.group(1))
        makefile = "physics_app/Makefile"
        if path.startswith("physics_app/src/") and makefile in source_names:
            for i, line in enumerate(contents[makefile][0].splitlines(), 1):
                if "include" in line and "$(FRAMEWORK_DIR)/app.mk" in line:
                    emit("file:" + makefile, "BUILD_OWNS_SOURCE", "file:" + path,
                         makefile, i, "APPLICATION_NAME=physics;source=" + path,
                         "BUILD_CONFIG_CANDIDATE")
                    result["build_ownership"].append({
                        "source_path": path, "build_config": makefile,
                        "source_blob_sha": contents[path][1],
                        "compile_status": "NOT_OBSERVED",
                        "link_status": "NOT_OBSERVED",
                        "evidence": witness(contents, makefile, i)})
                    break

    # Static Python input templates/type maps are NOT generated .i observations.
    routes = python_routes(contents, target, aliases)
    seen = set()
    for route in routes:
        key = (route["source"], route["line"], route["route_kind"],
               route["block_path_expression"])
        if key in seen:
            continue
        seen.add(key)
        outputs = sorted({e["to"].removeprefix("file:") for e in edges
                          if e["relation"] == "PYTHON_WRITES_INPUT"
                          and e["from"] == "file:" + route["source"]})
        if outputs:
            route["generated_input_path"] = outputs[0] if len(outputs) == 1 else "MULTIPLE_CANDIDATES"
            route["output_candidates"] = outputs
            route["output_evidence"] = "STATIC_WRITE_TARGET_NOT_RUNTIME_OUTPUT"
        result["generator_routes"].append(route)
        emit("file:" + route["source"], "GENERATOR_EMITS_OBJECT_CANDIDATE",
             "class:" + target, route["source"], route["line"],
             route["block_path_expression"] + ";type=" + route["factory_type"],
             "STATIC_TEMPLATE_NOT_EXECUTED")
        if not outputs and route["reference_scope"] != "TEST_OR_CHECKER_ONLY":
            unknown(route["source"], route["line"], "GENERATED_INPUT_NOT_TRACKED_OR_OBSERVED")

    # The provider graph is declarative: even one matching producer cannot prove effective resolution.
    producers = declared_providers(contents)
    for instance in instances:
        bindings = instance["bindings"]
        path = instance["input_path"]
        for binding in bindings:
            if binding["name"] not in FUNCTOR_PARAMS:
                continue
            raw = binding["raw_value"].strip("'\"")
            if not TOKEN.fullmatch(raw):
                unknown(path, binding["line"], "DYNAMIC_OR_COMPLEX_FUNCTOR_BINDING:" + binding["name"])
                continue
            matches = [p for p in producers if p["name"] == raw and p["path"] == path]
            status = ("UNKNOWN" if not matches else
                      "AMBIGUOUS_DECLARATIONS" if len(matches) > 1
                      else "SAME_FILE_DECLARED_CANDIDATE")
            record = {"instance_id": instance["instance_id"],
                      "parameter": binding["name"], "declared_name": raw,
                      "status": status, "effective_provider": "UNKNOWN",
                      "runtime_observation": "NOT_OBSERVED",
                      "candidate_producers": matches,
                      "evidence": witness(contents, path, binding["line"])}
            result["provider_bindings"].append(record)
            emit("functor:" + raw, "BINDS_PARAMETER", instance["instance_id"],
                 path, binding["line"], binding["name"] + "=" + raw,
                 "DECLARED_BINDING_ONLY")
            for producer in matches:
                emit("file:" + producer["path"], "PRODUCES_FUNCTOR_CANDIDATE",
                     "functor:" + raw, producer["path"], producer["evidence"]["line"],
                     producer["block_path"] + ":" + raw, "DECLARED_PROVIDER_ONLY")
            if not matches:
                unknown(path, binding["line"], "FUNCTOR_PROVIDER_NOT_PROVEN:" + binding["name"] + ":" + raw)
            elif len(matches) > 1:
                unknown(path, binding["line"], "AMBIGUOUS_FUNCTOR_PROVIDER:" + raw)

    # Workflow job and trigger declarations add context; no run attempt is observed.
    for edge in edges:
        if edge["relation"] != "WORKFLOW_RUNS_SCRIPT":
            continue
        path, line = edge["evidence"]["path"], edge["evidence"]["line"]
        text = contents[path][0]
        lines = text.splitlines()
        job = "UNKNOWN"
        in_jobs = False
        for row in lines[:line]:
            if row.startswith("jobs:"):
                in_jobs = True
            elif in_jobs and not row.startswith((" ", "\t", "#")) and row.strip():
                in_jobs = False
            match = re.match(r'^  ([A-Za-z_][\w-]*):\s*$', row)
            if in_jobs and match:
                job = match.group(1)
        triggers = [row.strip() for row in lines[:min(line, 100)]
                    if re.match(r'^\s*(?:on:|pull_request:|push:|workflow_dispatch:|paths:|paths-ignore:)', row)]
        entry = {"workflow_path": path, "job": job,
                 "script_path": edge["detail"],
                 "trigger_declarations": triggers[:20],
                 "execution": "NOT_OBSERVED",
                 "evidence": edge["evidence"]}
        edge["workflow_context"] = entry
        result["workflow_execution_paths"].append(entry)

    # Shell workflow intermediary to downstream Python; require a real tracked path.
    for path, (text, _) in sorted(contents.items()):
        if not path.endswith(".sh"):
            continue
        for line, raw in enumerate(text.splitlines(), 1):
            m = RUN.search(raw)
            if m and m.group(1).removeprefix("./") in source_names:
                emit("file:" + path, "SHELL_RUNS_SCRIPT",
                     "file:" + m.group(1).removeprefix("./"), path, line,
                     m.group(1), "STATIC_COMMAND_ONLY")

    # Imported external generator sources are named explicitly, but never equated with tracked .i.
    linked_generator_sources = {route["source"] for route in routes}
    for path, (text, _) in sorted(contents.items()):
        if not path.endswith(".py") or not path.startswith("experiments/"):
            continue
        if path not in linked_generator_sources and target not in text:
            continue
        if not ("generator" in text or "g337" in text):
            continue
        for line, raw in enumerate(text.splitlines(), 1):
            m = re.match(r'^from\s+(experiments\.[A-Za-z_][\w.]*)\s+import\s+([^\n#]+)', raw)
            if not m:
                continue
            module = m.group(1).replace(".", "/") + ".py"
            if module not in source_names:
                result["external_imports"].append({
                    "source": path, "module": m.group(1),
                    "resolved_tracked_path": None,
                    "role": "EXTERNAL_OR_HISTORICAL_IMPORT_NOT_REACHABLE",
                    "evidence": witness(contents, path, line)})

    for key in result:
        result[key].sort(key=lambda item: (
            item.get("source_path", item.get("source", item.get("instance_id", item.get("workflow_path", "")))),
            item.get("line", item.get("evidence", {}).get("line", 0)),
            item.get("parameter", "")))
    return result
