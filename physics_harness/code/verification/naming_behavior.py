"""Independent, source-bound behavior *falsification* for naming candidates.

Structural signatures can stay unchanged while a method silently changes its
body. We therefore compare exact Git object ASTs, but do not confuse matching
ASTs with semantic compatibility: module globals, imports, execution context,
identity/reflection, dynamic dispatch and external consumers remain unproven.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath

from ..diagnostics.providers.git import GitSourceProvider
from ..refactor.naming import NamingCase, NamingOption
from .naming_boundary import ResponsibilityBinding, _declaration_nodes
from .naming_candidate import CandidatePlacement, verify_naming_candidate


@dataclass(frozen=True, slots=True)
class ExecutableComparison:
    responsibility_id: str
    before_symbol: str
    after_symbol: str
    before_body_sha256: str
    after_body_sha256: str
    body_equal: bool
    hazards: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NamingBehaviorReceipt:
    baseline_revision: str
    candidate_revision: str
    option_id: str
    status: str  # STATIC_BODY_MATCH_ONLY / HOLD / REJECTED
    comparisons: tuple[ExecutableComparison, ...]
    blockers: tuple[str, ...]
    unresolved: tuple[str, ...]
    required_checks: tuple[str, ...]

    @property
    def mutation_approved(self) -> bool:
        return False

    @property
    def semantic_compatibility_proven(self) -> bool:
        return False


def _ast_symbols(source: bytes, path: str) -> tuple[dict[str, ast.AST], ast.Module]:
    tree = ast.parse(source.decode("utf-8", "strict"), filename=path, type_comments=True)
    symbols, _ = _declaration_nodes(tree, path)
    return symbols, tree


def _projection(node: ast.AST) -> str:
    # Deliberately retains executable expressions, literals, operators, call
    # targets and all statements; declaration *names* are handled separately.
    # This is NOT canonical semantic equivalence or a symbolic execution proof.
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        parts = node.body
    else:
        raise TypeError("UNSUPPORTED_BEHAVIOR_SYMBOL")
    return sha256("\n".join(ast.dump(x, include_attributes=False) for x in parts).encode()).hexdigest()


def _hazards(node: ast.AST, tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name) and child.func.id in {
                "eval", "exec", "getattr", "setattr", "delattr", "globals", "locals",
                "__import__", "vars", "compile",
            }:
                found.add("REFLECTION_OR_DYNAMIC_CALL:" + child.func.id)
            if isinstance(child.func, ast.Attribute) and child.func.attr in {
                "import_module", "loads", "load", "getattr", "setattr",
            }:
                found.add("INDIRECT_OR_SERIALIZATION_CALL:" + child.func.attr)
        elif isinstance(child, (ast.Global, ast.Nonlocal)):
            found.add("GLOBAL_OR_NONLOCAL_STATE")
        elif isinstance(child, (ast.Import, ast.ImportFrom)):
            found.add("IMPORT_INSIDE_EXECUTABLE")
        elif isinstance(child, (ast.Yield, ast.YieldFrom, ast.Await)):
            found.add("GENERATOR_OR_ASYNC_EXECUTION")
    if any(isinstance(item, (ast.Import, ast.ImportFrom)) for item in tree.body):
        found.add("MODULE_IMPORT_ENVIRONMENT_UNVERIFIED")
    if any(isinstance(item, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expr,
                             ast.If, ast.Try, ast.With, ast.For, ast.While))
           for item in tree.body):
        found.add("MODULE_INITIALIZATION_CONTEXT_UNVERIFIED")
    return found


def verify_naming_behavior_projection(
    case: NamingCase, option: NamingOption, provider: GitSourceProvider,
    bindings: tuple[ResponsibilityBinding, ...], candidate_revision: str,
    candidate_owner_path: str, placements: tuple[CandidatePlacement, ...],
    *, max_source_bytes: int = 2_000_000,
) -> NamingBehaviorReceipt:
    """Re-read exact Git before/after sources; ignore caller's PASS assertions.

    A matching code body is evidence *against one class of regression* only.
    A changed body is an obligation to replay behavior, not automatic proof of
    incompatibility. Never emits a semantic PASS or edit authorization.
    """
    if type(max_source_bytes) is not int or max_source_bytes < 1:
        raise ValueError("INVALID_BEHAVIOR_SOURCE_BUDGET")
    structural = verify_naming_candidate(
        case, option, provider, bindings, candidate_revision, candidate_owner_path,
        placements,
    )
    blocked = set(structural.blockers)
    unknown = set(structural.unresolved)
    checks = set(structural.required_checks) | {
        "INDEPENDENT_BEFORE_AFTER_EXECUTABLE_TEST_REPLAY",
        "VERIFY_IMPORT_RESOLUTION_GLOBALS_AND_SIDE_EFFECTS",
        "INDEPENDENT_BLINDED_RESPONSIBILITY_REVIEW",
        "VERIFY_EXTERNAL_AND_DYNAMIC_CONSUMERS",
    }
    comparisons = []
    if structural.status != "STRUCTURAL_DELTA_VERIFIED":
        unknown.add("STRUCTURAL_CANDIDATE_NOT_VERIFIED")
    else:
        cache = {}
        for p in placements:
            try:
                def read(rev: str, key: str):
                    path = key.split("::", 1)[0]
                    k = (rev, path)
                    if k not in cache:
                        record = provider.read_at_revision(rev, path)
                        if len(record.content) > max_source_bytes:
                            raise ValueError("SOURCE_BUDGET_EXCEEDED")
                        cache[k] = _ast_symbols(record.content, path)
                    return cache[k]
                before, before_tree = read(case.revision, p.before_symbol)
                after, after_tree = read(candidate_revision, p.after_symbol)
                before_node, after_node = before[p.before_symbol], after[p.after_symbol]
                d1, d2 = _projection(before_node), _projection(after_node)
                hazards = _hazards(before_node, before_tree) | _hazards(after_node, after_tree)
                if p.before_symbol != p.after_symbol:
                    hazards.add("SYMBOL_OR_MODULE_IDENTITY_CHANGED")
                if PurePosixPath(p.before_symbol.split("::")[0]) != PurePosixPath(p.after_symbol.split("::")[0]):
                    hazards.add("MODULE_RESOLUTION_CHANGED")
                if d1 != d2:
                    unknown.add("EXECUTABLE_AST_BODY_CHANGED:" + p.before_symbol)
                if hazards:
                    unknown.update(hazards)
                comparisons.append(ExecutableComparison(
                    p.responsibility_id, p.before_symbol, p.after_symbol, d1, d2,
                    d1 == d2, tuple(sorted(hazards)),
                ))
            except (KeyError, ValueError, TypeError, UnicodeError, SyntaxError) as exc:
                unknown.add("EXECUTABLE_SOURCE_UNRESOLVED:" + p.before_symbol + ":" + type(exc).__name__)
    status = "REJECTED" if blocked else "HOLD" if unknown else "STATIC_BODY_MATCH_ONLY"
    return NamingBehaviorReceipt(
        case.revision, candidate_revision, option.id, status,
        tuple(comparisons), tuple(sorted(blocked)), tuple(sorted(unknown)),
        tuple(sorted(checks)),
    )


__all__ = ["ExecutableComparison", "NamingBehaviorReceipt", "verify_naming_behavior_projection"]
