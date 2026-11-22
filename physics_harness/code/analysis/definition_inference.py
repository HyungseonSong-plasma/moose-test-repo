"""Bounded, name-blind definition hypotheses from source-declared interfaces.

The target folder/file name and README never enter the role inference stage.
This v0.2 lexical rule prototype does NOT prove behavioral/semantic ownership.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re

from libs.code_understandability.definition_metrics import (
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
