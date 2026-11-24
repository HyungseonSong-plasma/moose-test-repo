"""Exact-blob Python structural history facts for conservative Naming Audit.

Observes Python syntax and delegation seams only. Inferred responsibility,
logical identity, naming fitness and extraction safety remain independent gates.
Never reads README, scores CU, edits sources, or authorizes mutation.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from hashlib import sha1
from pathlib import PurePosixPath
import re


_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ValueError("INVALID_EVOLUTION_PATH")
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or str(p) != value or str(p) == ".":
        raise ValueError("INVALID_EVOLUTION_PATH")
    return value


def _source_ref(path: str, line: int, blob: str) -> str:
    return f"{path}:{line}@{blob}"


def _call_name(value: ast.AST) -> str | None:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        base = _call_name(value.value)
        return f"{base}.{value.attr}" if base else None
    return None


def _module_path(current_path: str, level: int, module: str | None) -> str | None:
    """Resolve *syntax* of relative/absolute from-import, not Python runtime imports."""
    base = list(PurePosixPath(current_path).parent.parts)
    if level:
        if level > len(base):
            return None
        base = base[:len(base) - level + 1]
    else:
        base = []
    if module:
        base.extend(module.split("."))
    if not base or any(not part.isidentifier() for part in base):
        return None
    return "/".join(base) + ".py"


@dataclass(frozen=True, slots=True)
class DeclaredClass:
    name: str
    bases: tuple[str, ...]
    methods: tuple[str, ...]
    source_ref: str

    @property
    def is_protocol(self) -> bool:
        return any(base == "Protocol" or base.endswith(".Protocol") for base in self.bases)


@dataclass(frozen=True, slots=True)
class DeclaredFunction:
    name: str
    source_ref: str


@dataclass(frozen=True, slots=True)
class ImportedSymbol:
    symbol: str
    local_name: str
    module: str
    resolved_path: str | None
    source_ref: str

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.module, self.symbol, self.local_name)


@dataclass(frozen=True, slots=True)
class SourceStructure:
    revision: str
    path: str
    blob_sha: str
    classes: tuple[DeclaredClass, ...]
    functions: tuple[DeclaredFunction, ...]
    imports: tuple[ImportedSymbol, ...]
    unknowns: tuple[str, ...] = ()

    @property
    def declared_keys(self) -> frozenset[str]:
        return frozenset([f"class:{x.name}" for x in self.classes] +
                         [f"function:{x.name}" for x in self.functions])


@dataclass(frozen=True, slots=True)
class DelegationSeam:
    """The owner imports another file's implementing class for a local protocol."""

    protocol: str
    imported_implementation: str
    implementation_path: str
    owner_import_ref: str
    protocol_ref: str
    implementation_ref: str
    matched_methods: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HistoryDelta:
    before_revision: str
    after_revision: str
    before_blob: str
    after_blob: str
    before_path: str
    after_path: str
    identity_status: str  # DECLARATION_OVERLAP_CANDIDATE / UNRESOLVED
    unchanged_definitions: tuple[str, ...]
    added_definitions: tuple[str, ...]
    removed_definitions: tuple[str, ...]
    added_imports: tuple[tuple[str, str, str], ...]
    removed_imports: tuple[tuple[str, str, str], ...]
    unknowns: tuple[str, ...]

    @property
    def mutation_approved(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class NamingEvolutionReceipt:
    """Evidence-only decision: naming and behavior still require independent review."""

    change: HistoryDelta
    existing_seams: tuple[DelegationSeam, ...]
    newly_observed_seams: tuple[DelegationSeam, ...]
    disposition: str  # KEEP_CONSIDERATION / EXTRACTION_REVIEW / HOLD
    unknowns: tuple[str, ...]
    required_checks: tuple[str, ...]

    @property
    def mutation_approved(self) -> bool:
        return False


def observe_python_structure(path: str, content: bytes, blob_sha: str,
                             revision: str) -> SourceStructure:
    """Require exact *bytes* for a declared Git blob; tree binding is external.

    A caller must use GitSourceProvider.read_at_revision (or equivalent) to
    independently establish path@revision -> blob. A matching caller-provided
    hash without that Git tree check is NOT revision provenance.
    """
    _path(path)
    if not path.endswith(".py"):
        raise ValueError("ONLY_PYTHON_SOURCE_SUPPORTED")
    if not isinstance(content, bytes) or not _SHA.fullmatch(blob_sha) or not _SHA.fullmatch(revision):
        raise ValueError("INVALID_SOURCE_IDENTITY")
    digest = sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()
    if blob_sha != digest:
        raise ValueError("EVOLUTION_BLOB_MISMATCH")
    text = content.decode("utf-8", "strict")
    tree = ast.parse(text, filename=path, type_comments=True)
    classes: list[DeclaredClass] = []
    functions: list[DeclaredFunction] = []
    imports: list[ImportedSymbol] = []
    unknowns: set[str] = set()
    dynamic_aliases = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "importlib"
        for alias in node.names if alias.name == "import_module"
    }
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(DeclaredClass(node.name,
                tuple(filter(None, (_call_name(base) for base in node.bases))),
                tuple(sorted(set(item.name for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))))),
                _source_ref(path, node.lineno, blob_sha)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(DeclaredFunction(node.name, _source_ref(path, node.lineno, blob_sha)))
    # Includes imports inside functions, as used by lazy collector registration.
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            resolved = _module_path(path, node.level, node.module)
            module = "." * node.level + (node.module or "")
            for alias in node.names:
                if alias.name == "*":
                    unknowns.add(f"WILDCARD_IMPORT:{path}:{node.lineno}")
                    continue
                imports.append(ImportedSymbol(alias.name, alias.asname or alias.name,
                                              module, resolved,
                                              _source_ref(path, node.lineno, blob_sha)))
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in {"eval", "exec", "getattr", "__import__", "importlib.import_module"} or name in dynamic_aliases:
                unknowns.add(f"DYNAMIC_REFERENCE:{path}:{node.lineno}")
    return SourceStructure(revision, path, blob_sha,
        tuple(sorted(classes, key=lambda c: c.name)),
        tuple(sorted(functions, key=lambda f: f.name)),
        tuple(sorted(imports, key=lambda i: (i.module, i.symbol, i.local_name, i.source_ref))),
        tuple(sorted(unknowns)))


def compare_source_history(before: SourceStructure, after: SourceStructure) -> HistoryDelta:
    if not isinstance(before, SourceStructure) or not isinstance(after, SourceStructure):
        raise TypeError("EVOLUTION_SNAPSHOTS_REQUIRED")
    if before.revision == after.revision:
        raise ValueError("EVOLUTION_REVISIONS_MUST_DIFFER")
    common = before.declared_keys & after.declared_keys
    unknowns = set(before.unknowns) | set(after.unknowns)
    if before.path != after.path:
        unknowns.add("MOVED_PATH_IDENTITY_NOT_VERIFIED")
    if not common:
        unknowns.add("NO_DECLARATION_CONTINUITY_WITNESS")
    if before.blob_sha != after.blob_sha:
        unknowns.add("FUNCTION_BODIES_NOT_SEMANTICALLY_COMPARED")
    # Even matching declared names cannot prove semantic identity or equivalence.
    identity = "DECLARATION_OVERLAP_CANDIDATE" if common else "UNRESOLVED"
    old_imports = {x.identity for x in before.imports}
    new_imports = {x.identity for x in after.imports}
    return HistoryDelta(before.revision, after.revision, before.blob_sha, after.blob_sha,
        before.path, after.path, identity, tuple(sorted(common)),
        tuple(sorted(after.declared_keys - before.declared_keys)),
        tuple(sorted(before.declared_keys - after.declared_keys)),
        tuple(sorted(new_imports - old_imports)),
        tuple(sorted(old_imports - new_imports)), tuple(sorted(unknowns)))


def find_delegation_seams(owner: SourceStructure,
                          available: tuple[SourceStructure, ...]) -> tuple[DelegationSeam, ...]:
    """Exact syntax witnesses; does NOT imply that extraction is needed or safe."""
    if not isinstance(owner, SourceStructure) or not isinstance(available, tuple) or any(
        not isinstance(x, SourceStructure) for x in available):
        raise TypeError("INVALID_DELEGATION_INPUT")
    if any(x.revision != owner.revision for x in available):
        raise ValueError("CROSS_REVISION_DELEGATION")
    if len({x.path for x in available}) != len(available):
        raise ValueError("DUPLICATE_IMPLEMENTATION_SOURCE")
    lookup = {x.path: x for x in available}
    seams: dict[tuple[str, str, str], DelegationSeam] = {}
    protocols = [x for x in owner.classes if x.is_protocol and x.methods]
    for imp in owner.imports:
        source = lookup.get(imp.resolved_path)
        if source is None or source.path == owner.path:
            continue
        for implementation in source.classes:
            if implementation.name != imp.symbol:
                continue
            for protocol in protocols:
                if not set(protocol.methods).issubset(implementation.methods):
                    continue
                item = DelegationSeam(protocol.name, implementation.name, source.path,
                    imp.source_ref, protocol.source_ref, implementation.source_ref,
                    protocol.methods)
                seams[(protocol.name, source.path, implementation.name)] = item
    return tuple(seams[x] for x in sorted(seams))


def audit_source_evolution(before: SourceStructure, after: SourceStructure,
                           before_owned: tuple[SourceStructure, ...],
                           after_owned: tuple[SourceStructure, ...]) -> NamingEvolutionReceipt:
    change = compare_source_history(before, after)
    prior = find_delegation_seams(before, before_owned)
    current = find_delegation_seams(after, after_owned)
    old = {(x.protocol, x.implementation_path, x.imported_implementation) for x in prior}
    added = tuple(x for x in current if
                  (x.protocol, x.implementation_path, x.imported_implementation) not in old)
    unknowns = set(change.unknowns)
    required = {"INDEPENDENT_RESPONSIBILITY_DEFINITION", "VERIFY_NAME_FIT_AND_BOUNDARY",
                "VERIFY_HISTORICAL_IDENTITY", "VERIFY_EXTERNAL_CONSUMER_SCOPE"}
    owned_protocols = [p for p in after.classes if p.is_protocol and p.methods]
    inline_implementations = [
        cls for cls in after.classes if not cls.is_protocol
        if any(set(proto.methods).issubset(cls.methods) for proto in owned_protocols)
    ]
    if change.identity_status == "UNRESOLVED" or change.before_path != change.after_path:
        disposition = "HOLD"
    elif added and not change.removed_definitions and not change.added_definitions:
        # Provider ownership already separated; recommend reviewing KEEP first.
        # Neither initial existence of a name nor added imports proves validity.
        disposition = "KEEP_CONSIDERATION"
    elif inline_implementations:
        disposition = "EXTRACTION_REVIEW"
        required.add("VERIFY_INLINE_IMPLEMENTATION_OWNERSHIP")
    else:
        disposition = "HOLD"
        unknowns.add("NO_RENAME_OR_EXTRACTION_JUSTIFICATION_FROM_SYNTAX")
    return NamingEvolutionReceipt(change, current, added, disposition,
                                  tuple(sorted(unknowns)), tuple(sorted(required)))


def audit_git_history(provider, before_revision: str, after_revision: str,
                      owner_path: str, *,
                      previous_owner_paths: tuple[str, ...] = (),
                      current_owner_paths: tuple[str, ...] = ()) -> NamingEvolutionReceipt:
    """Reconstruct historical evidence directly from immutable local Git trees.

    No worktree fallback, implicit fetch, or path-derived ownership claims.
    Incomplete checked-out history raises and must be marked HOLD by the caller.
    """
    from ..diagnostics.providers.git import GitSourceProvider
    if not isinstance(provider, GitSourceProvider):
        raise TypeError("GIT_SOURCE_PROVIDER_REQUIRED")
    for paths in (previous_owner_paths, current_owner_paths):
        if not isinstance(paths, tuple) or len(paths) > 100 or len(paths) != len(set(paths)):
            raise ValueError("INVALID_OWNER_INVENTORY")
        for path in paths:
            _path(path)
            if not path.endswith(".py"):
                raise ValueError("ONLY_PYTHON_SOURCE_SUPPORTED")
    _path(owner_path)
    if not _SHA.fullmatch(before_revision) or not _SHA.fullmatch(after_revision):
        raise ValueError("INVALID_HISTORY_REVISION")
    for revision in (before_revision, after_revision):
        try:
            if provider._git("cat-file", "-t", revision).strip() != b"commit":
                raise ValueError("HISTORY_COMMIT_UNAVAILABLE")
        except ValueError as exc:
            raise ValueError("HISTORY_COMMIT_UNAVAILABLE") from exc
    try:
        provider._git("merge-base", "--is-ancestor", before_revision, after_revision)
    except ValueError as exc:
        raise ValueError("HISTORY_REVISIONS_NOT_ANCESTRAL") from exc

    def read(revision: str, path: str) -> SourceStructure:
        original = provider.read_at_revision(revision, path)
        return observe_python_structure(path, original.content, original.record.blob_sha,
                                        revision)

    before = read(before_revision, owner_path)
    after = read(after_revision, owner_path)
    previous = tuple(read(before_revision, x) for x in previous_owner_paths)
    current = tuple(read(after_revision, x) for x in current_owner_paths)
    return audit_source_evolution(before, after, previous, current)


__all__ = ["DeclaredClass", "DeclaredFunction", "ImportedSymbol", "SourceStructure",
           "DelegationSeam", "HistoryDelta", "NamingEvolutionReceipt",
           "observe_python_structure", "compare_source_history",
           "find_delegation_seams", "audit_source_evolution", "audit_git_history"]
