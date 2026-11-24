"""Source-dependent verification and post-change checks.

A static-source PASS is not a proof of semantic or runtime equivalence.
"""

from __future__ import annotations

from dataclasses import dataclass
import ast
from collections.abc import Mapping

from ..diagnostics.collector import SourceInput, SourceProvider
from ..diagnostics.request import ScanRequest

from ..analysis.diff import GraphDiff, compare_graphs
from ..diagnostics.receipt import EvidenceReceipt
from ..graph import GraphSnapshot
from .consistency import verify_generated_artifact


@dataclass(frozen=True, slots=True)
class ChangeVerificationPlan:
    before_revision: str
    after_revision: str
    change: GraphDiff
    required_checks: tuple[str, ...]
    impacted_subjects: tuple[str, ...]
    findings: tuple[str, ...]
    disposition: str

    @property
    def mutation_approved(self) -> bool:
        # Source graph comparison cannot itself approve a repository edit.
        return False


def plan_change_verification(
    before: GraphSnapshot, after: GraphSnapshot,
    before_receipt: EvidenceReceipt, after_receipt: EvidenceReceipt,
) -> ChangeVerificationPlan:
    """Derive work from observed structural changes, not naming policies."""
    first = verify_generated_artifact(before, before_receipt)
    second = verify_generated_artifact(after, after_receipt)
    diff = compare_graphs(before, after)
    findings = set(first.failures + second.failures)
    checks: set[str] = set()
    subjects = set(
        diff.added_nodes + diff.removed_nodes + diff.changed_nodes
        + diff.added_edges + diff.removed_edges + diff.changed_edges
    )

    if first.status != "VERIFIED" or second.status != "VERIFIED":
        checks.add("RESOLVE_SOURCE_PROVENANCE_AND_COVERAGE")
    if diff.removed_nodes or diff.removed_edges:
        checks.add("VERIFY_REMOVED_CONSUMERS_AND_REFERENCES")
    if diff.added_nodes or diff.changed_nodes:
        checks.add("VERIFY_CHANGED_DECLARATIONS_AND_INTERFACES")
    if diff.added_edges or diff.changed_edges or diff.removed_edges:
        checks.add("VERIFY_DEPENDENCY_AND_CALL_IMPACT")
    if any(
        edge.relation.endswith("_CANDIDATE")
        for edge in after.edges if edge.id in set(diff.added_edges + diff.changed_edges)
    ):
        checks.add("RESOLVE_CANDIDATE_DEPENDENCIES")
    if diff.coverage_changed or diff.new_unresolved:
        checks.add("VERIFY_SCOPE_AND_UNRESOLVED_DELTA")
    if (diff.added_evidence or diff.removed_evidence or diff.changed_evidence
            or subjects):
        checks.add("REPLAY_IMPACTED_TESTS_AT_AFTER_HEAD")
    if checks:
        checks.add("VERIFY_BEHAVIORAL_COMPATIBILITY")
    if first.repository != second.repository:
        findings.add("CROSS_REPOSITORY_CHANGE")
    return ChangeVerificationPlan(
        before_revision=first.revision, after_revision=second.revision,
        change=diff, required_checks=tuple(sorted(checks)),
        impacted_subjects=tuple(sorted(subjects)),
        findings=tuple(sorted(findings)),
        disposition="BLOCKED" if findings else (
            "UNVERIFIED" if checks else "VERIFIED_SOURCE_ONLY"
        ),
    )




@dataclass(frozen=True, slots=True)
class DependencyRule:
    source: str
    target: str
    category: str
    reason: str
    except_source: str = ""

    def matches(self, source: str | None, target: str | None) -> bool:
        return (source is not None and target == self.target
                and self.source in ("*", source) and source != self.except_source)


@dataclass(frozen=True, slots=True)
class DependencyContract:
    """Repository policies are passed as data; Harness contains no package bans."""

    package_root: str
    canonical_packages: tuple[str, ...]
    legacy_packages: tuple[str, ...]
    forbidden_edges: tuple[DependencyRule, ...]
    repository_tool: str
    repository_tool_allowed_sources: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "DependencyContract":
        if not isinstance(value, Mapping) or value.get("schema_version") != 1:
            raise ValueError("DEPENDENCY_CONTRACT_SCHEMA")
        try:
            contract = cls(
                package_root=value["package_root"],
                canonical_packages=tuple(value["canonical_packages"]),
                legacy_packages=tuple(value["legacy_packages"]),
                forbidden_edges=tuple(
                    DependencyRule(**entry) for entry in value["forbidden_edges"]
                ),
                repository_tool=value["repository_tool"],
                repository_tool_allowed_sources=tuple(value.get("repository_tool_allowed_sources", ())),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("DEPENDENCY_CONTRACT_INVALID") from exc
        allowed = set(contract.canonical_packages) | set(contract.legacy_packages)
        if (not contract.package_root or not contract.repository_tool
                or len(allowed) != len(contract.canonical_packages) + len(contract.legacy_packages)
                or not contract.canonical_packages or not contract.forbidden_edges
                or any(source not in contract.canonical_packages for source in contract.repository_tool_allowed_sources)
                or any(rule.source not in allowed | {"*"} or rule.target not in allowed
                       or (rule.except_source and rule.except_source not in allowed)
                       or not rule.category or not rule.reason
                       for rule in contract.forbidden_edges)):
            raise ValueError("DEPENDENCY_CONTRACT_INVALID")
        return contract


@dataclass(frozen=True, slots=True)
class DependencyFinding:
    category: str
    path: str
    line: int
    source: str
    target: str
    blob_sha: str
    reason: str


@dataclass(frozen=True, slots=True)
class DependencyVerification:
    status: str
    checked_files: int
    findings: tuple[DependencyFinding, ...]
    unverified_properties: tuple[str, ...]

    @property
    def mutation_approved(self) -> bool:
        return False


def _package(module: str, contract: DependencyContract) -> str | None:
    parts = module.split(".")
    names = set(contract.canonical_packages) | set(contract.legacy_packages)
    return (parts[1] if len(parts) >= 2 and
            parts[0] == contract.package_root and parts[1] in names else None)


def _cycle(graph: dict[str, set[str]]) -> tuple[str, ...]:
    active: set[str] = set()
    done: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> tuple[str, ...]:
        if node in active:
            return tuple(stack[stack.index(node):] + [node])
        if node in done:
            return ()
        active.add(node)
        stack.append(node)
        for target in sorted(graph.get(node, ())):
            found = visit(target)
            if found:
                return found
        stack.pop()
        active.remove(node)
        done.add(node)
        return ()

    for node in sorted(graph):
        found = visit(node)
        if found:
            return found
    return ()


def _record_earliest_line(lines: dict[str, int], target: str, line: int) -> None:
    """Keep the earliest *source* line, not the first breadth-first AST visit."""
    previous = lines.get(target)
    if previous is None or line < previous:
        lines[target] = line


def verify_dependencies(
    sources: tuple[SourceInput, ...], contract: DependencyContract,
) -> DependencyVerification:
    """Check absolute Python imports, repository references and package cycles.

    The caller must supply all scoped sources via an authenticated exact-HEAD
    provider. Dynamic/relative import resolution and runtime are not proven.
    """
    if not isinstance(contract, DependencyContract):
        raise TypeError("DEPENDENCY_CONTRACT_REQUIRED")
    if not isinstance(sources, tuple) or any(
        not isinstance(item, SourceInput) for item in sources
    ):
        raise TypeError("DEPENDENCY_SOURCE_INPUT_REQUIRED")
    graph = {name: set() for name in contract.canonical_packages}
    witnesses: dict[tuple[str, str], tuple[str, int, str]] = {}
    findings: list[DependencyFinding] = []
    seen: set[str] = set()
    incomplete = False

    for item in sorted(sources, key=lambda source: source.record.path):
        record = item.record
        path = record.path
        if (path in seen or not path.startswith(contract.package_root + "/")
                or not path.endswith(".py")):
            incomplete = True
            continue
        seen.add(path)
        module = path[:-3].replace("/", ".")
        if module.endswith(".__init__"):
            module = module[:-9]
        src = _package(module, contract)
        try:
            tree = ast.parse(item.content.decode("utf-8"), filename=path)
        except (SyntaxError, UnicodeError):
            incomplete = True
            continue

        imports: dict[str, int] = {}
        repository_refs: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    _record_earliest_line(imports, alias.name, node.lineno)
                    if alias.name == contract.repository_tool or alias.name.startswith(
                        contract.repository_tool + "."
                    ):
                        _record_earliest_line(repository_refs, alias.name, node.lineno)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                _record_earliest_line(imports, node.module, node.lineno)
                if node.module == contract.repository_tool or node.module.startswith(
                    contract.repository_tool + "."
                ):
                    _record_earliest_line(repository_refs, node.module, node.lineno)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value == contract.repository_tool or node.value.startswith(
                    contract.repository_tool + "/"
                ):
                    _record_earliest_line(repository_refs, node.value, node.lineno)

        for target, line in sorted(imports.items()):
            dst = _package(target, contract)
            if src is None or dst is None:
                continue
            for rule in contract.forbidden_edges:
                if rule.matches(src, dst):
                    findings.append(DependencyFinding(
                        rule.category, path, line, module, target,
                        record.blob_sha, rule.reason,
                    ))
                    break  # preserve the legacy first-matching-category semantics
            if src in graph and dst in graph and src != dst:
                graph[src].add(dst)
                witnesses.setdefault((src, dst), (path, line, record.blob_sha))

        for target, line in sorted(repository_refs.items()):
            if src in contract.repository_tool_allowed_sources:
                continue
            findings.append(DependencyFinding(
                "repository", path, line, module, target, record.blob_sha,
                "production source refers to repository tooling",
            ))

    cycle = _cycle(graph)
    if cycle:
        path, line, blob_sha = witnesses.get((cycle[0], cycle[1]), ("", 0, ""))
        findings.append(DependencyFinding(
            "cycle", path, line, cycle[0], " -> ".join(cycle), blob_sha,
            "canonical dependency cycle",
        ))
    unknown = ("DYNAMIC_OR_RELATIVE_IMPORTS_UNPROVEN",
               "SEMANTIC_AND_RUNTIME_COMPATIBILITY_UNPROVEN")
    if incomplete or not seen:
        unknown = ("INCOMPLETE_SOURCE_COVERAGE",) + unknown
    return DependencyVerification(
        status="UNVERIFIED" if incomplete or not seen else (
            "FAIL" if findings else "PASS"
        ),
        checked_files=len(seen),
        findings=tuple(sorted(findings, key=lambda x: (
            x.category, x.path, x.line, x.source, x.target
        ))),
        unverified_properties=unknown,
    )


def verify_dependency_repository(
    request: ScanRequest, provider: SourceProvider,
    contract: DependencyContract,
) -> DependencyVerification:
    """Verify the complete tracked Python package at one exact Git HEAD."""
    if (request.includes != (contract.package_root + "/*.py",)
            or request.excludes):
        raise ValueError("DEPENDENCY_SCOPE_NOT_FULL_PACKAGE")
    records = provider.inventory(request)
    selected = tuple(
        item for item in records if item.path.startswith(
            contract.package_root + "/"
        ) and item.path.endswith(".py")
    )
    if (len(selected) > request.budget.max_files
            or sum(item.size for item in selected) > request.budget.max_bytes):
        return DependencyVerification(
            "UNVERIFIED", 0, (),
            ("SOURCE_BUDGET_EXCEEDED",),
        )
    sources = tuple(SourceInput(item, provider.read(item)) for item in selected)
    return verify_dependencies(sources, contract)


__all__ = [
    "ChangeVerificationPlan", "DependencyContract", "DependencyFinding",
    "DependencyRule", "DependencyVerification", "plan_change_verification",
    "verify_dependencies", "verify_dependency_repository",
]
