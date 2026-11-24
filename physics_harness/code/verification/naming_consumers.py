"""Exact Git source repository-internal consumer impact for naming changes.

The inventory is bounded and is deliberately not an external-consumer proof:
static imports, literal references and dynamic import candidates are separate.
Internal source scans cannot establish compatibility with other repositories,
entry-point metadata, persisted imports or runtime introspection.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from subprocess import TimeoutExpired

from ..diagnostics.providers.git import GitSourceProvider
from ..diagnostics.request import normalized_path
from ..refactor.naming import NamingCase, NamingOption
from .naming_candidate import CandidatePlacement


_TEXT_EXTENSIONS = frozenset({
    ".py", ".toml", ".cfg", ".ini", ".json", ".yaml", ".yml",
    ".md", ".rst", ".txt", ".sh", ".cmake", ".cpp", ".hpp", ".h", ".C",
})
_DYNAMIC_CALLS = frozenset({"__import__", "eval", "exec", "getattr", "globals", "locals"})


@dataclass(frozen=True, slots=True)
class ConsumerReference:
    path: str
    revision: str
    source_ref: str
    category: str  # STATIC_IMPORT / DYNAMIC_CANDIDATE / TEXT_LITERAL
    detail: str


@dataclass(frozen=True, slots=True)
class NamingConsumerReceipt:
    baseline_revision: str
    candidate_revision: str
    option_id: str
    status: str  # BLOCKED / HOLD / INTERNAL_SCAN_WITH_EXTERNAL_GAPS
    scanned_files: int
    before_references: tuple[ConsumerReference, ...]
    after_references: tuple[ConsumerReference, ...]
    blockers: tuple[str, ...]
    unresolved: tuple[str, ...]
    required_checks: tuple[str, ...]

    @property
    def mutation_approved(self) -> bool:
        return False

    @property
    def external_consumers_verified(self) -> bool:
        return False


def _git_source_paths(provider: GitSourceProvider, revision: str) -> tuple[str, ...]:
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("INVALID_CONSUMER_REVISION")
    if provider._git("cat-file", "-t", revision).strip() != b"commit":
        raise ValueError("CONSUMER_REVISION_NOT_COMMIT")
    return tuple(sorted(path for path in provider._regular_tree_paths(revision)
                        if PurePosixPath(path).suffix in _TEXT_EXTENSIONS))


def _module_for(path: str) -> str:
    if not path.endswith(".py"):
        return ""
    s = path[:-3].replace("/", ".")
    return s[:-9] if s.endswith(".__init__") else s


def _resolve_from(file: str, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    module = _module_for(file)
    package = module.split(".") if file.endswith("/__init__.py") else module.split(".")[:-1]
    if node.level > len(package):
        return ""  # unresolved relative import, not enough package context
    base = package[:len(package) - node.level + 1]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def _scan_revision(provider: GitSourceProvider, revision: str,
                   old_module: str, old_name: str | None,
                   *, max_files: int, max_bytes: int) -> tuple[tuple[ConsumerReference, ...], tuple[str, ...], int]:
    refs: set[ConsumerReference] = set()
    problems: set[str] = set()
    count = 0
    total = 0
    paths = _git_source_paths(provider, revision)
    if len(paths) > max_files:
        problems.add("REPOSITORY_CONSUMER_FILE_BUDGET_EXCEEDED")
        paths = paths[:max_files]
    old_path = old_module.replace(".", "/") + ".py"
    # Never accept an unbounded basename-only text search. Normal code tokens
    # are evaluated via syntax; text literals must include a qualified module.
    literal_re = re.compile(r"(?<![A-Za-z0-9_.])(?:" + re.escape(old_module) +
                            r"|" + re.escape(old_path) + r")(?![A-Za-z0-9_.])")
    for path in paths:
        try:
            src = provider.read_at_revision(revision, path)
            count += 1
            total += len(src.content)
            if total > max_bytes:
                problems.add("REPOSITORY_CONSUMER_BYTE_BUDGET_EXCEEDED")
                break
            if b"\x00" in src.content:
                problems.add("UNSCANNED_CONSUMER_BINARY_SOURCE:" + path)
                continue
            value = src.content.decode("utf-8", "strict")
            lines = value.splitlines()
            blob = src.record.blob_sha
            if path.endswith(".py"):
                tree = ast.parse(value, filename=path)
                for node in ast.walk(tree):
                    category = "STATIC_IMPORT"
                    if isinstance(node, ast.Import):
                        details = tuple(alias.name for alias in node.names
                                        if alias.name == old_module
                                        or alias.name.startswith(old_module + "."))
                    elif isinstance(node, ast.ImportFrom):
                        target = _resolve_from(path, node)
                        if node.level and not target:
                            problems.add("RELATIVE_IMPORT_RESOLUTION_UNKNOWN:" + path)
                        if not (target == old_module or target.startswith(old_module + ".")
                                or any(target + "." + alias.name == old_module for alias in node.names)):
                            continue
                        details = tuple(f"from:{target}:{alias.name}" for alias in node.names
                                        if old_name is None or alias.name == old_name
                                        or target == old_module)
                    elif isinstance(node, ast.Call):
                        func = node.func
                        val = func.id if isinstance(func, ast.Name) else (
                            func.attr if isinstance(func, ast.Attribute) else "")
                        if val not in _DYNAMIC_CALLS and val not in {"import_module", "loads", "load"}:
                            continue
                        # Dynamic calls do not prove a renamed-symbol dependency.
                        category, details = "DYNAMIC_CANDIDATE", (val,)
                    else:
                        continue
                    refs.update(ConsumerReference(path, revision,
                                f"{path}:{node.lineno}@{blob}", category, detail)
                                for detail in details)
            for idx, line in enumerate(lines, 1):
                if literal_re.search(line):
                    refs.add(ConsumerReference(path, revision, f"{path}:{idx}@{blob}",
                                               "TEXT_LITERAL", line.strip()[:160]))
        except (ValueError, UnicodeError, SyntaxError) as exc:
            problems.add("UNSCANNED_CONSUMER_SOURCE:" + path + ":" + type(exc).__name__)
    return tuple(sorted(refs, key=lambda r: (r.path, r.source_ref, r.category, r.detail))), tuple(sorted(problems)), count


def audit_naming_consumers(
    case: NamingCase, option: NamingOption, provider: GitSourceProvider,
    candidate_revision: str, placements: tuple[CandidatePlacement, ...],
    *, max_files: int = 3000, max_bytes: int = 20_000_000,
) -> NamingConsumerReceipt:
    """Scan both exact Git trees; flag broken imports, text and dynamic gaps.

    A scan without findings never establishes external consumer closure.
    """
    if not isinstance(case, NamingCase) or not isinstance(option, NamingOption):
        raise TypeError("CONSUMERS_CASE_OPTION_REQUIRED")
    if not isinstance(provider, GitSourceProvider) or not isinstance(placements, tuple) or any(
        not isinstance(x, CandidatePlacement) for x in placements):
        raise TypeError("CONSUMERS_PROVIDER_PLACEMENTS_REQUIRED")
    if type(max_files) is not int or max_files < 1 or type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("INVALID_CONSUMER_BUDGET")
    blocked: set[str] = set()
    unknown: set[str] = {"EXTERNAL_CONSUMERS_NOT_SCANNED"}
    checks = {"VERIFY_EXTERNAL_DEPENDENTS_AND_PUBLIC_IMPORT_CONTRACTS",
              "VERIFY_DYNAMIC_IMPORTS_REFLECTION_AND_SERIALIZATION",
              "REPLAY_IMPORT_AND_RUNTIME_TESTS_AT_CANDIDATE_HEAD"}
    if option.variant in {"KEEP", "HOLD"}:
        blocked.add("NO_EDIT_CONSUMER_AUDIT_FOR_KEEP_OR_HOLD")
    if candidate_revision == case.revision:
        blocked.add("CONSUMER_CANDIDATE_MUST_BE_NEW_COMMIT")
    else:
        try:
            provider._git("merge-base", "--is-ancestor", case.revision, candidate_revision)
        except ValueError:
            blocked.add("CONSUMER_CANDIDATE_NOT_DESCENDANT")
    # A changed class/function name inside an unchanged module also has public
    # import consumers. Extraction can move a function while keeping its name.
    affected: set[tuple[str, str | None]] = set()
    for placement in placements:
        before_path, before_member = placement.before_symbol.split("::", 1)
        after_path, after_member = placement.after_symbol.split("::", 1)
        if (before_path, before_member) != (after_path, after_member):
            name = before_member.split(":", 1)[-1].split(".", 1)[0]
            affected.add((_module_for(before_path), name))
    if case.target_kind in {"FILE", "FOLDER"} and case.current_path.endswith(".py"):
        affected.add((_module_for(case.current_path), None))
    if not affected:
        unknown.add("NO_DECLARED_RENAMED_OR_MOVED_SYMBOLS")
    before = []
    after = []
    count = 0
    for module, name in sorted(affected, key=lambda pair: (pair[0], pair[1] or "")):
        try:
            b, errors_b, nb = _scan_revision(provider, case.revision, module, name,
                                max_files=max_files, max_bytes=max_bytes)
            a, errors_a, na = _scan_revision(provider, candidate_revision, module, name,
                                max_files=max_files, max_bytes=max_bytes)
            before.extend(b)
            after.extend(a)
            count += nb + na
            unknown.update(errors_b)
            unknown.update(errors_a)
            # If a source module was deleted, all old static imports are broken,
            # regardless of other changes that happen to retain identifiers.
            old_path = module.replace(".", "/") + ".py"
            old_exists = True
            try:
                provider.read_at_revision(candidate_revision, old_path)
            except (ValueError, TypeError):
                old_exists = False
            bad = [v for v in a if v.category == "STATIC_IMPORT" and v.path != old_path]
            if bad and not old_exists:
                blocked.add("STALE_IMPORT_TO_REMOVED_MODULE:" + module)
            elif bad:
                unknown.add("RETAINED_OLD_MODULE_IMPORT_REQUIRES_EXPORT_CHECK:" + module)
            if any(v.category == "TEXT_LITERAL" and v.path != old_path for v in a):
                unknown.add("LITERAL_REFERENCE_REQUIRES_REVIEW:" + module)
            if any(v.category == "DYNAMIC_CANDIDATE" for v in a):
                unknown.add("DYNAMIC_CONSUMERS_PRESENT")
            if name and old_exists and bad:
                # Static source can re-export imported symbols; AST declarations
                # alone cannot certify the shim. Leave it to behavior tests.
                unknown.add("MOVED_OR_RENAMED_SYMBOL_EXPORT_UNVERIFIED:" + name)
        except (ValueError, UnicodeError, TypeError) as exc:
            unknown.add("CONSUMER_INVENTORY_UNAVAILABLE:" + type(exc).__name__)
    return NamingConsumerReceipt(
        case.revision, candidate_revision, option.id,
        "BLOCKED" if blocked else "HOLD" if unknown - {"EXTERNAL_CONSUMERS_NOT_SCANNED"} else
        "INTERNAL_SCAN_WITH_EXTERNAL_GAPS",
        count, tuple(sorted(set(before), key=lambda x:(x.path,x.source_ref,x.category,x.detail))),
        tuple(sorted(set(after), key=lambda x:(x.path,x.source_ref,x.category,x.detail))),
        tuple(sorted(blocked)), tuple(sorted(unknown)), tuple(sorted(checks)),
    )


@dataclass(frozen=True, slots=True)
class ModulePathTransitionReceipt:
    """Source-bound path policy evidence, not runtime or mutation approval."""
    baseline_revision: str
    candidate_revision: str
    old_path: str
    new_path: str
    policy: str
    status: str  # BLOCKED / HOLD
    old_path_present: bool | None
    new_path_present: bool | None
    path_policy_witnessed: bool
    references: tuple[ConsumerReference, ...]
    scanned_files: int
    blockers: tuple[str, ...]
    unresolved: tuple[str, ...]

    @property
    def mutation_approved(self) -> bool:
        return False


def _module_entry(provider: GitSourceProvider, revision: str, path: str) -> str | None:
    """Observe trees, symlinks and gitlinks; absence is not a read error."""
    rows = provider._git("ls-tree", "--full-tree", "-z", revision,
                         "--", ":(literal)" + path).split(b"\0")
    entries = []
    for row in rows:
        if not row:
            continue
        meta, filename = row.split(b"\t", 1)
        mode, kind, sha = meta.decode("ascii").split()
        if filename.decode("utf-8", "strict") != path:
            raise ValueError("MODULE_TREE_ENTRY_MISMATCH")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("MODULE_TREE_ENTRY_INVALID")
        entries.append(mode)
    if len(entries) > 1:
        raise ValueError("MODULE_TREE_ENTRY_AMBIGUOUS")
    return entries[0] if entries else None


def verify_module_path_transition(
    provider: GitSourceProvider, baseline_revision: str, candidate_revision: str,
    old_path: str, new_path: str, policy: str, *,
    max_files: int = 3000, max_bytes: int = 20_000_000,
) -> ModulePathTransitionReceipt:
    """Check a module move or retirement of an already migrated shim.

    Package paths use __init__.py. Retirement also forbids the old directory
    and alternate .py form. Compatibility requires a regular retained file,
    but its exports and runtime behavior still need independent verification.
    """
    if not isinstance(provider, GitSourceProvider):
        raise TypeError("MODULE_TRANSITION_PROVIDER_REQUIRED")
    if policy not in {"PRESERVE_COMPATIBILITY", "RETIRE_OLD_PATH"}:
        raise ValueError("INVALID_MODULE_PATH_POLICY")
    if type(max_files) is not int or max_files < 1 or type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("INVALID_CONSUMER_BUDGET")
    for path in (old_path, new_path):
        normalized_path(path)
        if (not path.endswith(".py") or path == "__init__.py" or "." in path[:-3]
                or not all(part.isidentifier() for part in _module_for(path).split("."))):
            raise ValueError("INVALID_PYTHON_MODULE_PATH")
    if _module_for(old_path) == _module_for(new_path):
        raise ValueError("MODULE_TRANSITION_REQUIRES_DISTINCT_PATHS")
    for revision in (baseline_revision, candidate_revision):
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("INVALID_MODULE_TRANSITION_REVISION")
    blocked: set[str] = set()
    unknown = {"EXTERNAL_CONSUMERS_NOT_SCANNED", "DYNAMIC_AND_SERIALIZED_CONTRACTS_UNPROVEN"}
    refs: tuple[ConsumerReference, ...] = ()
    count = 0
    old_present = new_present = None
    witnessed = False
    if baseline_revision == candidate_revision:
        blocked.add("MODULE_TRANSITION_REQUIRES_DISTINCT_COMMIT")
    else:
        try:
            for revision in (baseline_revision, candidate_revision):
                if provider._git("cat-file", "-t", revision).strip() != b"commit":
                    raise ValueError("MODULE_TRANSITION_NOT_COMMIT")
            provider._git("merge-base", "--is-ancestor", baseline_revision, candidate_revision)
            provider.read_at_revision(baseline_revision, old_path)
            module = _module_for(old_path)
            module_root = module.replace(".", "/")
            old_entry = _module_entry(provider, candidate_revision, old_path)
            old_present = any(_module_entry(provider, candidate_revision, path) is not None
                              for path in (module_root + ".py", module_root))
            new_entry = _module_entry(provider, candidate_revision, new_path)
            new_present = new_entry is not None
            if new_entry not in {"100644", "100755"}:
                blocked.add("CANONICAL_MODULE_MISSING_OR_NONREGULAR:" + new_path)
            else:
                provider.read_at_revision(candidate_revision, new_path)
            if policy == "PRESERVE_COMPATIBILITY":
                if old_entry not in {"100644", "100755"}:
                    blocked.add("REQUIRED_COMPATIBILITY_PATH_MISSING_OR_NONREGULAR:" + old_path)
                else:
                    provider.read_at_revision(candidate_revision, old_path)
                    unknown.add("COMPATIBILITY_EXPORTS_AND_BEHAVIOR_UNVERIFIED")
            elif old_present:
                blocked.add("RETIRED_MODULE_PATH_STILL_PRESENT:" + old_path)
            witnessed = not blocked
            refs, issues, count = _scan_revision(provider, candidate_revision, module, None,
                                                 max_files=max_files, max_bytes=max_bytes)
            unknown.update(issues)
            if policy == "RETIRE_OLD_PATH" and any(
                    ref.category == "STATIC_IMPORT" for ref in refs):
                blocked.add("STALE_IMPORT_TO_RETIRED_MODULE:" + module)
            if any(ref.category == "TEXT_LITERAL" for ref in refs):
                unknown.add("LITERAL_REFERENCE_REQUIRES_REVIEW:" + module)
            if any(ref.category == "DYNAMIC_CANDIDATE" for ref in refs):
                unknown.add("DYNAMIC_CONSUMERS_PRESENT")
        except (ValueError, TypeError, UnicodeError, TimeoutExpired) as exc:
            unknown.add("MODULE_TRANSITION_SOURCE_OR_ANCESTRY_UNPROVEN:" + type(exc).__name__)
    return ModulePathTransitionReceipt(
        baseline_revision, candidate_revision, old_path, new_path, policy,
        "BLOCKED" if blocked else "HOLD", old_present, new_present, witnessed,
        refs, count, tuple(sorted(blocked)), tuple(sorted(unknown)))


__all__ = ["ConsumerReference", "NamingConsumerReceipt", "audit_naming_consumers",
           "ModulePathTransitionReceipt", "verify_module_path_transition"]
