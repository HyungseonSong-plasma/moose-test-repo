"""Independent exact-source responsibility-to-symbol / extraction boundary witness.

Checks *source declarations and intended ownership*, NOT whether a declared
responsibility is semantically true, whether dynamic clients are closed, or whether
any edit is authorized. No hardcoded domain vocabulary, package placement or name
ranking. Source inventory is read from the Git commit tree, never the worktree.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import PurePosixPath
import re

from ..diagnostics.providers.git import GitSourceProvider
from ..diagnostics.request import normalized_path
from ..refactor.naming import NamingCase, NamingOption, review_naming_option

_SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True, slots=True)
class OwnedSymbol:
    """Observed declaration key: source/path.py::class:X / function:y / method:X.z."""

    key: str
    source_ref: str
    signature: str


@dataclass(frozen=True, slots=True)
class ResponsibilityBinding:
    """Independent reviewer assertion to test against observed source syntax.

    The reviewer must provide precise symbol keys, not only prose. Syntax can
    corroborate the existence of a declaration, not the meaning assigned to it.
    """

    responsibility_id: str
    source_symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.responsibility_id, str) or not self.responsibility_id:
            raise ValueError("INVALID_BOUND_RESPONSIBILITY")
        if (not isinstance(self.source_symbols, tuple) or not self.source_symbols
                or any(not isinstance(s, str) or "::" not in s for s in self.source_symbols)
                or len(set(self.source_symbols)) != len(self.source_symbols)):
            raise ValueError("INVALID_BOUND_SYMBOLS")


@dataclass(frozen=True, slots=True)
class NamingBoundaryReceipt:
    revision: str
    option_id: str
    status: str  # STRUCTURE_WITNESSED / HOLD / REJECTED
    observed_symbols: tuple[OwnedSymbol, ...]
    verified_bindings: tuple[str, ...]
    unbound_owner_declarations: tuple[str, ...]
    existing_destinations: tuple[str, ...]
    blockers: tuple[str, ...]
    unresolved: tuple[str, ...]
    required_checks: tuple[str, ...]

    @property
    def semantic_compatibility_proven(self) -> bool:
        return False

    @property
    def mutation_approved(self) -> bool:
        return False


def _tree_paths(provider: GitSourceProvider, revision: str) -> frozenset[str]:
    """Exact commit inventory, including regular Python files only."""
    if not _SHA.fullmatch(revision):
        raise ValueError("INVALID_BOUNDARY_REVISION")
    if provider._git("cat-file", "-t", revision).strip() != b"commit":
        raise ValueError("BOUNDARY_REVISION_NOT_COMMIT")
    rows = provider._git("ls-tree", "--full-tree", "-r", "-z", revision).split(b"\0")
    paths = set()
    for row in rows:
        if not row:
            continue
        meta, name = row.split(b"\t", 1)
        mode, typ, sha = meta.decode("ascii").split()
        if typ != "blob" or mode not in {"100644", "100755"}:
            continue
        path = name.decode("utf-8", "strict")
        if path.endswith(".py"):
            paths.add(normalized_path(path))
    return frozenset(paths)


def _declaration_inventory(tree: ast.Module, path: str) -> tuple[list[tuple[str, ast.AST]], set[str]]:
    """Keep direct declarations and identify keys that cannot bind uniquely.

    Conditional declarations are not supported bindings. Record their keys as
    unresolved, including when they compete with an otherwise direct declaration.
    Nested local functions are not module/class owner declarations.
    """
    declarations: list[tuple[str, ast.AST]] = []
    seen: set[str] = set()
    ambiguous: set[str] = set()
    functions = (ast.FunctionDef, ast.AsyncFunctionDef)

    def add(key: str, node: ast.AST, direct: bool) -> None:
        if not direct or key in seen:
            ambiguous.add(key)
        if direct:
            seen.add(key)
            declarations.append((key, node))

    def visit(node: ast.AST, owner: str | None = None, direct: bool = False) -> None:
        if isinstance(node, functions):
            key = (f"method:{owner}.{node.name}" if owner is not None
                   else f"function:{node.name}")
            add(path + "::" + key, node, direct)
            return
        if isinstance(node, ast.ClassDef):
            if owner is not None:
                return  # nested classes are outside the supported owner inventory
            add(path + "::class:" + node.name, node, direct)
            for item in node.body:
                visit(item, node.name, direct)
            return
        # Descending through compound statements does not establish ownership.
        for child in ast.iter_child_nodes(node):
            visit(child, owner, False)

    for stmt in tree.body:
        visit(stmt, direct=True)
    for key in seen:
        if "::method:" in key:
            parent = key.split("::method:", 1)[1].split(".", 1)[0]
            if path + "::class:" + parent in ambiguous:
                ambiguous.add(key)
    return declarations, ambiguous


def _declaration_nodes(tree: ast.Module, path: str) -> tuple[dict[str, ast.AST], set[str]]:
    declarations, ambiguous = _declaration_inventory(tree, path)
    return {key: node for key, node in declarations if key not in ambiguous}, ambiguous


def _key_in_scope(key: str, kind: str, path: str, name: str) -> bool:
    if kind == "FOLDER":
        return key.split("::", 1)[0].startswith(path.rstrip("/") + "/")
    if not key.startswith(path + "::"):
        return False
    if kind == "FILE":
        return True
    if kind == "CLASS":
        return (key == path + "::class:" + name
                or key.startswith(path + "::method:" + name + "."))
    return kind == "FUNCTION" and key == path + "::function:" + name


def _symbol_inventory(provider: GitSourceProvider, revision: str,
                      paths: tuple[str, ...], *, ambiguous: set[str] | None = None
                      ) -> tuple[OwnedSymbol, ...]:
    observed = []
    for path in paths:
        source = provider.read_at_revision(revision, path)
        body = ast.parse(source.content.decode("utf-8", "strict"), filename=path)
        sha = source.record.blob_sha
        declarations, collisions = _declaration_inventory(body, path)
        if ambiguous is not None:
            ambiguous.update(collisions)
        def declare(key: str, node: ast.AST, *, args: ast.AST | None = None):
            # Method/function signatures are compared structurally, not executed.
            signature = ast.dump(args, include_attributes=False) if args else ""
            if isinstance(node, ast.ClassDef):
                signature = repr((tuple(ast.dump(b, include_attributes=False) for b in node.bases),
                                  tuple(ast.dump(k, include_attributes=False) for k in node.keywords),
                                  tuple(ast.dump(d, include_attributes=False) for d in node.decorator_list)))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                signature = repr(("async" if isinstance(node, ast.AsyncFunctionDef) else "sync",
                                  signature, ast.dump(node.returns, include_attributes=False)
                                  if node.returns is not None else None,
                                  tuple(ast.dump(d, include_attributes=False) for d in node.decorator_list)))
            observed.append(OwnedSymbol(key,
                         f"{path}:{node.lineno}@{sha}", signature))
        for key, node in declarations:
            declare(key, node, args=node.args if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)) else None)
    return tuple(sorted(observed, key=lambda x: x.key))


def _source_scope(case: NamingCase, all_paths: frozenset[str]) -> tuple[str, ...]:
    """Precisely bound class/function/file/folder to a pinned source inventory."""
    if case.target_kind == "FOLDER":
        base = normalized_path(case.current_path).rstrip("/") + "/"
        return tuple(sorted(p for p in all_paths if p.startswith(base)))
    path = normalized_path(case.current_path)
    return (path,) if path in all_paths else ()


def _relevant_symbols(case: NamingCase,
                      symbols: tuple[OwnedSymbol, ...]) -> tuple[OwnedSymbol, ...]:
    if case.target_kind in {"FILE", "FOLDER"}:
        return symbols
    prefix = ("class:" if case.target_kind == "CLASS" else "function:") + case.current_name
    target = case.current_path + "::" + prefix
    keys = {x.key for x in symbols}
    if target not in keys:
        return ()
    if case.target_kind == "CLASS":
        return tuple(x for x in symbols if x.key == target or
                     x.key.startswith(case.current_path + "::method:" + case.current_name + "."))
    return tuple(x for x in symbols if x.key == target)


def verify_naming_boundary(
    case: NamingCase, option: NamingOption, provider: GitSourceProvider,
    bindings: tuple[ResponsibilityBinding, ...], *, max_files: int = 64,
    max_bytes: int = 2_000_000,
) -> NamingBoundaryReceipt:
    """Check responsibility-symbol *anchors* and extraction placement at exact HEAD.

    Validating a declaration is not validating its claimed responsibility.  A
    resulting STRUCTURE_WITNESSED receipt is **not** semantic clearance. A
    post-change candidate verifier is still necessary before any edit approval.
    """
    if not isinstance(case, NamingCase) or not isinstance(option, NamingOption):
        raise TypeError("BOUNDARY_CASE_AND_OPTION_REQUIRED")
    if not isinstance(provider, GitSourceProvider):
        raise TypeError("BOUNDARY_GIT_PROVIDER_REQUIRED")
    if not isinstance(bindings, tuple) or any(not isinstance(b, ResponsibilityBinding) for b in bindings):
        raise TypeError("BOUNDARY_BINDINGS_REQUIRED")
    if type(max_files) is not int or max_files < 1 or type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("INVALID_BOUNDARY_BUDGET")
    blocked: set[str] = set()
    unresolved: set[str] = set()
    checks: set[str] = {"INDEPENDENT_RESPONSIBILITY_INTERPRETATION",
                       "VERIFY_CONSUMER_AND_DYNAMIC_REFERENCE_CLOSURE",
                       "VERIFY_ACTUAL_BEFORE_AFTER_BEHAVIOR_AND_PUBLIC_CONTRACTS"}
    declared = {b.responsibility_id: b for b in bindings}
    if len(declared) != len(bindings):
        blocked.add("DUPLICATE_RESPONSIBILITY_BINDING")
    if set(declared) - set(case.responsibility_ids):
        blocked.add("INVENTED_BOUND_RESPONSIBILITY")
    missing = set(case.responsibility_ids) - set(declared)
    if missing:
        unresolved.update("RESPONSIBILITY_NOT_BOUND:" + x for x in missing)
    from .naming_provenance import verify_naming_evidence_sources
    provenance = verify_naming_evidence_sources(case, provider)
    blocked.update(provenance.failures)
    unresolved.update(provenance.unresolved)
    if provenance.status != "SOURCE_ANCHORS_VERIFIED":
        unresolved.add("ALL_NAMING_SOURCE_ANCHORS_NOT_VERIFIED")
    review = review_naming_option(case, option)
    blocked.update(review.blockers)
    unresolved.update(review.unknowns)
    if review.disposition not in {"REVIEWABLE", "BASELINE"}:
        unresolved.add("NAMING_OPTION_NOT_REVIEWABLE")
    if case.target_kind not in {"FOLDER", "FILE", "CLASS", "FUNCTION"}:
        blocked.add("UNSUPPORTED_NAMING_TARGET")
    if case.identity_status != "RESOLVED":
        unresolved.add("LOGICAL_IDENTITY_UNRESOLVED")
    if case.unknowns:
        unresolved.update(case.unknowns)
    all_paths: frozenset[str] = frozenset()
    observed: tuple[OwnedSymbol, ...] = ()
    scope = ()
    ambiguous: set[str] = set()
    try:
        all_paths = _tree_paths(provider, case.revision)
        scope = _source_scope(case, all_paths)
        if not scope:
            unresolved.add("TARGET_PYTHON_SOURCE_NOT_FOUND")
        elif len(scope) > max_files:
            unresolved.add("SOURCE_FILE_BUDGET_EXCEEDED")
        else:
            # Read exact source once through Git objects to bound scan cost.
            total = 0
            for path in scope:
                record = provider.read_at_revision(case.revision, path)
                total += len(record.content)
                if total > max_bytes:
                    unresolved.add("SOURCE_BYTE_BUDGET_EXCEEDED")
                    break
            if not any(x.endswith("BUDGET_EXCEEDED") for x in unresolved):
                observed = _relevant_symbols(case, _symbol_inventory(
                    provider, case.revision, scope, ambiguous=ambiguous))
                if not observed:
                    unresolved.add("TARGET_DECLARATIONS_UNRESOLVED")
    except (ValueError, UnicodeError, SyntaxError) as exc:
        unresolved.add("EXACT_SOURCE_OR_AST_UNAVAILABLE:" + type(exc).__name__)
    ambiguous = {key for key in ambiguous if _key_in_scope(
        key, case.target_kind, case.current_path, case.current_name)}
    unresolved.update("AMBIGUOUS_DECLARATION:" + key for key in ambiguous)
    by_key = {x.key: x for x in observed if x.key not in ambiguous}
    evidence = {e.id: e for e in case.evidence}
    verified = []
    for rid, binding in declared.items():
        if rid not in evidence or evidence[rid].kind != "RESPONSIBILITY":
            blocked.add("BINDING_NOT_TO_RESPONSIBILITY_EVIDENCE:" + rid)
            continue
        if evidence[rid].source_revision != case.revision:
            unresolved.add("RESPONSIBILITY_NOT_ON_CURRENT_REVISION:" + rid)
        for key in binding.source_symbols:
            if key in ambiguous:
                continue  # an observed collision is not a missing declaration
            symbol = by_key.get(key)
            if symbol is None:
                if not observed:
                    unresolved.add("BOUND_SYMBOL_OWNER_UNAVAILABLE:" + key)
                else:
                    blocked.add("BOUND_SYMBOL_NOT_OWNED:" + key)
            elif symbol.source_ref not in evidence[rid].source_refs:
                # Arbitrary in-file citations must not establish ownership.
                unresolved.add("RESPONSIBILITY_CITATION_NOT_DECLARATION:" + rid + ":" + key)
            else:
                verified.append(rid + "=" + key)
    # A model can assign only its favorite few declarations to responsibilities
    # while silently ignoring other module/class owners. An editing candidate
    # cannot be cleared even at *structural* level without a complete inventory.
    bound_keys = {sym for b in bindings for sym in b.source_symbols}
    assigned_top = set(bound_keys)
    for key in bound_keys:
        if "::method:" in key:
            path, member = key.split("::method:", 1)
            assigned_top.add(path + "::class:" + member.split(".", 1)[0])
    unbound = tuple(sorted(s.key for s in observed
                           if "::method:" not in s.key and s.key not in assigned_top))
    if unbound and option.variant not in {"KEEP", "HOLD"}:
        unresolved.add("OWNER_DECLARATION_INVENTORY_NOT_ACCOUNTED")
    # Detect duplicate owner-specific assignments. One actual symbol may serve
    # different responsibilities; this is not necessarily invalid, but splitting
    # it physically into different new owners has not been justified.
    owner_for: dict[str, set[str]] = {}
    if option.variant.startswith("EXTRACT_"):
        ownership = {r: set() for r in case.responsibility_ids}
        for rid in option.retained_responsibility_ids:
            ownership.setdefault(rid, set()).add("original")
        for unit in option.extracted_units:
            for rid in unit.responsibility_ids:
                ownership.setdefault(rid, set()).add(unit.owner_id)
        for rid, b in declared.items():
            owners = ownership.get(rid, set())
            if not owners:
                blocked.add("RESPONSIBILITY_WITHOUT_POST_OWNER:" + rid)
            for sym in b.source_symbols:
                owner_for.setdefault(sym, set()).update(owners)
        for symbol, owners in owner_for.items():
            if len(owners) > 1:
                unresolved.add("SHARED_SYMBOL_SPLIT_NEEDS_BEHAVIORAL_SEAM:" + symbol)
        for unit in option.extracted_units:
            if unit.destination_path is None:
                unresolved.add("DESTINATION_PATH_NOT_DECLARED:" + unit.owner_id)
                continue
            path = unit.destination_path
            if not path.endswith(".py"):
                unresolved.add("NON_PYTHON_EXTRACTION_REQUIRES_OTHER_COLLECTOR:" + path)
                continue
            present = path in all_paths
            if unit.destination_existing and not present:
                blocked.add("DECLARED_EXISTING_OWNER_NOT_FOUND:" + path)
            elif not unit.destination_existing and present:
                blocked.add("NEW_EXTRACTION_PATH_ALREADY_EXISTS:" + path)
            elif unit.destination_existing:
                try:
                    dest_ambiguities: set[str] = set()
                    dest = _symbol_inventory(provider, case.revision, (path,),
                                             ambiguous=dest_ambiguities)
                    # A full-file/folder extraction depends on the destination inventory.
                    # For bounded declarations only the selected owner names are relevant.
                    bound_names = {key.split("::", 1)[1] for rid in unit.responsibility_ids
                                   if rid in declared for key in declared[rid].source_symbols}
                    for key in dest_ambiguities:
                        name = key.split("::", 1)[1]
                        if (case.target_kind in {"FILE", "FOLDER"} or name in bound_names
                                or any(name.startswith("method:" + n[6:] + ".")
                                       for n in bound_names if n.startswith("class:"))):
                            unresolved.add("AMBIGUOUS_DECLARATION:" + key)
                    if not dest:
                        unresolved.add("DESTINATION_HAS_NO_DECLARATIONS:" + path)
                    before_names = {s.split("::", 1)[1] for rid in unit.responsibility_ids
                                    if rid in declared for s in declared[rid].source_symbols}
                    destination_names = {s.key.split("::", 1)[1] for s in dest}
                    if before_names & destination_names:
                        unresolved.add("POSSIBLE_DUPLICATE_IMPLEMENTATION_ALREADY_OWNED:" + path)
                except (ValueError, UnicodeError, SyntaxError) as exc:
                    unresolved.add("DESTINATION_SOURCE_UNAVAILABLE:" + type(exc).__name__)
            if path == case.current_path:
                blocked.add("EXTRACTION_DESTINATION_SAME_AS_SOURCE:" + path)
    elif option.variant == "RENAME":
        if option.extracted_units:
            blocked.add("RENAME_MUST_NOT_EXTRACT")
    status = "REJECTED" if blocked else "HOLD" if unresolved else "STRUCTURE_WITNESSED"
    return NamingBoundaryReceipt(case.revision, option.id, status, observed,
        tuple(sorted(set(verified))), unbound,
        tuple(sorted(unit.destination_path for unit in option.extracted_units
                     if unit.destination_existing and unit.destination_path in all_paths)),
        tuple(sorted(blocked)), tuple(sorted(unresolved)), tuple(sorted(checks)))


__all__ = ["OwnedSymbol", "ResponsibilityBinding", "NamingBoundaryReceipt",
           "verify_naming_boundary"]
