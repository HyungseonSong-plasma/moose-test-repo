"""Bounded, name-blind definition hypotheses from source-declared interfaces.

The target folder/file name and README never enter the role inference stage.
This v0.2 lexical rule prototype does NOT prove behavioral/semantic ownership.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re

from libs.code_lucidity.definition_metrics import (
    DefinitionClause, NameCue, lexical_tokens, measure_definition,
)

# Generic AND predicates, independent of target paths. Rules are versioned and
# diagnostic, not policy; unknown/contradictory cases remain unresolved.
RULE_VERSION = "definition-signature-v0.2"
ROLE_RULES = (
    ("REPRESENT", ("claim", "evidence", "node", "edge")),
    ("COLLECT", ("scan", "source", "fact")),
    ("ANALYZE", ("analyze", "assess", "impact")),
    ("PLAN", ("planning", "alternative", "review")),
    ("VERIFY", ("verification", "verify", "dependency")),
)


@dataclass(frozen=True)
class SourceSymbol:
    identifier: str
    source_ref: str  # path:line@sha where available; never a fabricated line
    origin: str = "PUBLIC_API"  # IMPLEMENTED_OWNER is only for locally resolved declarations


@dataclass(frozen=True)
class DefinitionInference:
    role: str | None
    clauses: tuple[DefinitionClause, ...]
    matched_symbols: tuple[str, ...]
    evidence_level: str
    ambiguities: tuple[str, ...]


def infer_from_symbols(symbols: tuple[SourceSymbol, ...]) -> DefinitionInference:
    """No target name or README argument; public symbols remain lexical evidence."""
    if not isinstance(symbols, tuple) or not all(isinstance(s, SourceSymbol) for s in symbols):
        raise TypeError("SOURCE_SYMBOLS_REQUIRED")
    words: dict[str, set[str]] = {}
    for symbol in symbols:
        if not symbol.source_ref or not symbol.identifier:
            raise ValueError("SYMBOL_SOURCE_REQUIRED")
        for term in lexical_tokens(symbol.identifier):
            words.setdefault(term, set()).add(symbol.source_ref)
    matches = tuple((role, concepts) for role, concepts in ROLE_RULES
                    if all(term in words for term in concepts))
    if len(matches) != 1:
        return DefinitionInference(None, (), (), "UNRESOLVED", (
            "NO_MATCHING_ROLE" if not matches else "MULTIPLE_ROLE_CANDIDATES",
        ))
    role, concepts = matches[0]
    refs = tuple(sorted({s.identifier for s in symbols
                         if lexical_tokens(s.identifier).intersection(concepts)}))
    return DefinitionInference(
        role=role,
        clauses=tuple(DefinitionClause(word, tuple(sorted(words[word]))) for word in concepts),
        matched_symbols=refs,
        evidence_level=("IMPLEMENTED_OWNER" if all(s.origin == "IMPLEMENTED_OWNER" for s in symbols)
                        else "PUBLIC_API_DECLARED"),
        ambiguities=("LEXICAL_API_SIGNATURE_NOT_BEHAVIORAL_PROOF",),
    )


def extract_public_symbols_from_folder(root: Path, folder: str) -> tuple[SourceSymbol, ...]:
    """Resolve __all__ against declarations in direct Python modules.

    All files must be a locally available trusted exact-head checkout. Does
    not import modules or execute their code. Unknown reexports stay unresolved.
    """
    folder_path = root / folder
    if not folder_path.is_dir():
        raise FileNotFoundError(folder_path)
    resolved = folder_path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("SOURCE_PATH_OUTSIDE_ROOT")
    imports: dict[str, str] = {}
    definitions: dict[str, tuple[str, int]] = {}
    exports: list[str] | None = None
    for source in sorted(folder_path.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(source))
        rel = source.relative_to(root).as_posix()
        if source.name == "__init__.py":
            for statement in tree.body:
                if isinstance(statement, ast.ImportFrom) and statement.level == 1 and statement.module:
                    for alias in statement.names:
                        imports[alias.asname or alias.name] = statement.module
                if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    if isinstance(statement, ast.Assign):
                        is_all = any(isinstance(t, ast.Name) and t.id == "__all__" for t in statement.targets)
                    else:
                        is_all = isinstance(statement.target, ast.Name) and statement.target.id == "__all__"
                    if is_all:
                        try:
                            raw = ast.literal_eval(statement.value)
                        except (ValueError, TypeError) as exc:
                            raise ValueError("UNSUPPORTED_PUBLIC_EXPORTS") from exc
                        if not isinstance(raw, (list, tuple)) or not all(isinstance(x, str) for x in raw):
                            raise ValueError("UNSUPPORTED_PUBLIC_EXPORTS")
                        exports = list(raw)
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                module = source.relative_to(folder_path).with_suffix("").as_posix().replace("/", ".")
                definitions[(module + ":" + node.name)] = (rel, node.lineno)
    if exports is None:
        raise ValueError("MISSING_EXPLICIT_PUBLIC_EXPORTS")
    results = []
    for symbol in exports:
        owner_module = imports.get(symbol, "__init__")
        found = definitions.get(owner_module + ":" + symbol)
        if found is None:
            results.append(SourceSymbol(symbol, (folder + "/__init__.py"), "PUBLIC_API"))
        else:
            results.append(SourceSymbol(symbol, f"{found[0]}:{found[1]}", "IMPLEMENTED_OWNER"))
    return tuple(results)


def make_folder_cues(path: str, symbols: tuple[SourceSymbol, ...],
                     direct_module_names: tuple[str, ...]) -> tuple[NameCue, ...]:
    """Construct disclosure protocol *after* name-blind definition inference."""
    p = Path(path)
    if not p.name or str(p) == ".":
        raise ValueError("INVALID_TARGET_FOLDER")
    cues = [NameCue("name", p.name, 0, path),
            NameCue("parent", p.parent.name, 1, p.parent.as_posix())]
    for module in sorted(set(direct_module_names)):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", module):
            raise ValueError("INVALID_MODULE_CUE")
        cues.append(NameCue("module:"+module, module, 2, path + "/"+module+".py"))
    for symbol in sorted(symbols, key=lambda s: (s.identifier, s.source_ref)):
        cues.append(NameCue("api:"+symbol.identifier, symbol.identifier, 3, symbol.source_ref))
    return tuple(cues)


def measure_folder(path: str, symbols: tuple[SourceSymbol, ...],
                   direct_module_names: tuple[str, ...]) -> dict:
    """Inference remains independent of the target name; measurement does not."""
    inferred = infer_from_symbols(symbols)
    if not inferred.clauses:
        return {"path": path, "status": "UNRESOLVED", "role": None,
                "reasons": list(inferred.ambiguities), "metrics": None}
    cues = make_folder_cues(path, symbols, direct_module_names)
    result = measure_definition(inferred.clauses, cues)
    return {"path": path, "status": "MEASURED_LEXICAL_PROXY",
            "role": inferred.role, "evidence_level": inferred.evidence_level,
            "clauses": [{"concept": c.concept,"source_refs": c.source_refs} for c in inferred.clauses],
            "reasons": list(inferred.ambiguities),
            "metrics": {
                "DEB": result.definition_explanation_burden,
                "DEB_denominator": result.total_concepts,
                "DEB_fraction": result.explanation_burden_fraction,
                "MRC_extra_cues": result.minimum_required_context,
                "MRC_tier": result.minimum_context_tier,
                "MRC_cues": result.selected_context_cues,
                "unpredicted_baseline": result.unpredicted_concepts,
                "not_recoverable_in_scope": result.still_unrecoverable,
            }}


# v0.3: independently observed Python AST behavior (not lexical API role names)
# The source extractor is conservative: calls are syntactic, never runtime proof.
import hashlib
from pathlib import PurePosixPath

BEHAVIOR_RULE_VERSION = "definition-behavior-v0.3"
BEHAVIOR_RULES = (
    ("GRAPH_MODEL", ("FROZEN_RECORD", "RELATIONAL_FIELDS"),
     ("record", "relation", "invariant")),
    ("SOURCE_FACT_COLLECTION", ("SOURCE_PARSE", "GRAPH_FACT_CONSTRUCTION"),
     ("source", "parse", "evidence")),
    ("GRAPH_ANALYSIS", ("GRAPH_TRAVERSAL", "ANALYSIS_RESULT"),
     ("graph", "analysis", "result")),
    ("CHANGE_PLANNING", ("OPTIONS_ITERATION", "OPTION_VALIDATION"),
     ("option", "constraint", "review")),
    ("SOURCE_VERIFICATION", ("PROVENANCE_COMPARISON", "VERIFICATION_RESULT"),
     ("source", "provenance", "verification")),
)


@dataclass(frozen=True)
class BehaviorWitness:
    kind: str
    source_ref: str  # path:line@exact-git-blob
    observation: str  # syntactic statement; no semantic-completeness assertion


@dataclass(frozen=True)
class BehaviorFileScan:
    path: str
    revision: str
    blob_sha: str
    witnesses: tuple[BehaviorWitness, ...]
    unknowns: tuple[str, ...] = ()


@dataclass(frozen=True)
class BehaviorDefinition:
    role: str | None
    clauses: tuple[DefinitionClause, ...]
    status: str
    evidence: tuple[BehaviorWitness, ...]
    missing: tuple[str, ...]
    unknowns: tuple[str, ...]
    rule_version: str = BEHAVIOR_RULE_VERSION
    role_candidates: tuple[str, ...] = ()


def _call_name(expr: ast.expr) -> str:
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        root = _call_name(expr.value)
        return root + "." + expr.attr if root else expr.attr
    return ""


def _is_frozen_dataclass(node: ast.ClassDef) -> bool:
    return any(isinstance(d, ast.Call) and _call_name(d.func).endswith("dataclass")
               and any(k.arg == "frozen" and isinstance(k.value, ast.Constant)
                       and k.value.value is True for k in d.keywords)
               for d in node.decorator_list)


def _relative_python_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("BEHAVIOR_INVALID_PATH")
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or p.as_posix() != value or not value.endswith(".py"):
        raise ValueError("BEHAVIOR_INVALID_PATH")
    return value


def extract_behavior_witnesses(path: str, source: str, blob_sha: str,
                               revision: str) -> BehaviorFileScan:
    """Inspect trusted, UTF-8 tracked Python source with Git-blob verification.

    Names of the *target* folder, class and function are never used as role
    classification features. Typed field names, called interfaces, and
    observed control/data flow are explicit evidence, not hidden semantics.
    """
    _relative_python_path(path)
    if not isinstance(source, str) or not isinstance(blob_sha, str) or not isinstance(revision, str):
        raise TypeError("BEHAVIOR_SOURCE_IDENTITY_REQUIRED")
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or not re.fullmatch(r"[0-9a-f]{40}", blob_sha):
        raise ValueError("BEHAVIOR_EXACT_SHA_REQUIRED")
    payload = source.encode("utf-8")
    actual_blob = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
    if actual_blob != blob_sha:
        raise ValueError("BEHAVIOR_SOURCE_BLOB_MISMATCH")
    tree = ast.parse(source, filename=path, type_comments=True)
    facts: dict[tuple[str, int], BehaviorWitness] = {}
    unknowns = set()

    def add(kind: str, node: ast.AST, observation: str) -> None:
        line = getattr(node, "lineno", None)
        if line is None:
            return
        facts[(kind, line)] = BehaviorWitness(kind, f"{path}:{line}@{blob_sha}", observation)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _is_frozen_dataclass(node):
            fields = {v.target.id for v in node.body if isinstance(v, ast.AnnAssign)
                      and isinstance(v.target, ast.Name)}
            if fields:
                add("FROZEN_RECORD", node, "immutable annotated record declaration")
            # A target_id+scope_id result/receipt does not own a graph relation.
            # Require the relation endpoints or an explicit claim-evidence pair.
            if ({"source_id", "target_id"} <= fields or
                    {"subject_refs", "evidence_refs"} <= fields):
                add("RELATIONAL_FIELDS", node, "relation endpoints or claim-to-evidence pair declared")
        elif isinstance(node, ast.Call):
            call = _call_name(node.func)
            terminal = call.split(".")[-1]
            if call in {"ast.parse", "tokenize.detect_encoding", "json.loads", "yaml.safe_load"}:
                add("SOURCE_PARSE", node, "recognized source decode/parse API")
            if terminal in {"FactBatch", "Node", "Edge", "Evidence"}:
                add("GRAPH_FACT_CONSTRUCTION", node, "graph/evidence fact constructor candidate")
            if terminal in {"unfold_context", "nodes_by_id", "evidence_by_id", "edges_by_id"}:
                add("GRAPH_TRAVERSAL", node, "graph/context traversal call candidate")
            if terminal in {"ImpactResult", "Assessment", "AnalysisRecord", "Claim"}:
                add("ANALYSIS_RESULT", node, "analysis/report constructor candidate")
            if terminal == "validate_alternative":
                add("OPTION_VALIDATION", node, "independent alternative validation call candidate")
            if terminal in {"VerificationReceipt", "DependencyVerification"}:
                add("VERIFICATION_RESULT", node, "verification result constructor candidate")
            if terminal in {"write_text", "write_bytes", "unlink", "rmtree", "delete_file"} or call in {"os.remove", "os.system", "subprocess.Popen", "subprocess.run"}:
                add("EXTERNAL_SINK_CANDIDATE", node, "possible external write/process side effect")
            if terminal in {"getattr", "eval", "exec", "__import__", "import_module"}:
                unknowns.add(f"DYNAMIC_OR_INDIRECT_CALL:{path}:{node.lineno}")
        elif isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.iter, ast.Name) and node.iter.id == "alternatives":
            add("OPTIONS_ITERATION", node, "iterates explicitly supplied alternatives")
        elif isinstance(node, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
            if any(isinstance(comp.iter, ast.Name) and comp.iter.id == "alternatives" for comp in node.generators):
                add("OPTIONS_ITERATION", node, "comprehension iterates explicitly supplied alternatives")
        elif isinstance(node, ast.Compare):
            attributes = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
            if attributes.intersection({"revision", "scope_id", "blob_sha", "source_sha"}):
                add("PROVENANCE_COMPARISON", node, "source/scope identity compared")
        elif isinstance(node, ast.Raise):
            add("REJECTION_PATH", node, "explicit rejection/exception path")
    return BehaviorFileScan(path, revision, blob_sha,
                            tuple(facts[k] for k in sorted(facts, key=lambda x: (x[1], x[0]))),
                            tuple(sorted(unknowns)))


def infer_from_behavior(scans: tuple[BehaviorFileScan, ...],
                        *, required_paths: tuple[str, ...]) -> BehaviorDefinition:
    """Bounded role hypotheses; never certify all consumers or semantic behavior."""
    if not isinstance(scans, tuple) or not all(isinstance(s, BehaviorFileScan) for s in scans):
        raise TypeError("BEHAVIOR_SCANS_REQUIRED")
    if not isinstance(required_paths, tuple) or not required_paths:
        raise ValueError("BEHAVIOR_REQUIRED_PATHS_MISSING")
    required = {_relative_python_path(p) for p in required_paths}
    if len(required) != len(required_paths):
        raise ValueError("BEHAVIOR_DUPLICATE_REQUIRED_PATH")
    paths = {s.path for s in scans}
    if len(paths) != len(scans):
        raise ValueError("BEHAVIOR_DUPLICATE_SCAN")
    if paths - required:
        raise ValueError("BEHAVIOR_UNDECLARED_SOURCE")
    if len({s.revision for s in scans}) > 1:
        raise ValueError("BEHAVIOR_CROSS_REVISION")
    missing = tuple(sorted(required - paths))
    evidence = tuple(w for s in scans for w in s.witnesses)
    by_kind: dict[str, list[BehaviorWitness]] = {}
    for w in evidence:
        by_kind.setdefault(w.kind, []).append(w)
    matches = tuple((role, concepts) for role, needed, concepts in BEHAVIOR_RULES
                    if all(by_kind.get(k) for k in needed))
    problems = set(u for s in scans for u in s.unknowns)
    if missing:
        problems.add("MISSING_REQUIRED_SOURCE")
    if any(w.kind == "EXTERNAL_SINK_CANDIDATE" for w in evidence):
        problems.add("EXTERNAL_EFFECTS_REQUIRE_REVIEW")
    if len(matches) != 1:
        problems.add("NO_BEHAVIOR_ROLE" if not matches else "MULTIPLE_BEHAVIOR_ROLES")
        return BehaviorDefinition(None, (), "UNRESOLVED", evidence, missing, tuple(sorted(problems)),
                                  role_candidates=tuple(role for role, _ in matches))
    role, concepts = matches[0]
    selected = next(needed for label, needed, _ in BEHAVIOR_RULES if role == label)
    refs = tuple(sorted({w.source_ref for k in selected for w in by_kind[k]}))
    clauses = tuple(DefinitionClause(word, refs) for word in concepts)
    return BehaviorDefinition(role, clauses,
                              "CANDIDATE_WITH_GAPS" if problems else "CANDIDATE_WITHIN_SCOPE",
                              evidence, missing, tuple(sorted(problems)))
