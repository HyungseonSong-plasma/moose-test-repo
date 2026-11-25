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
    independent_packages: tuple[str, ...] = ()

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
                independent_packages=tuple(value.get("independent_packages", ())),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("DEPENDENCY_CONTRACT_INVALID") from exc
        allowed = set(contract.canonical_packages) | set(contract.legacy_packages)
        if (not contract.package_root or not contract.repository_tool
                or len(allowed) != len(contract.canonical_packages) + len(contract.legacy_packages)
                or not contract.canonical_packages
                or (not contract.forbidden_edges and not contract.independent_packages)
                or len(set(contract.independent_packages)) != len(contract.independent_packages)
                or not set(contract.independent_packages) <= set(contract.canonical_packages)
                or any(not isinstance(p, str) or not p.isidentifier()
                       for p in contract.independent_packages)
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
    if contract.independent_packages:
        raise ValueError("DESIGN_ONLY_DEPENDENCY_CONTRACT")
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


@dataclass(frozen=True, slots=True)
class DependencyObservation:
    """A source-declared import, execution or resource candidate; not runtime proof."""
    category: str
    path: str
    line: int
    source: str
    target: str
    blob_sha: str
    evidence_id: str


@dataclass(frozen=True, slots=True)
class DependencyDesignReport:
    revision: str
    scope_id: str
    status: str
    observations: tuple[DependencyObservation, ...]
    findings: tuple[DependencyFinding, ...]
    cycle: tuple[str, ...]
    unknowns: tuple[str, ...]
    required_paths: tuple[str, ...]

    @property
    def runtime_independence_proven(self) -> bool:
        return False

    @property
    def mutation_approved(self) -> bool:
        return False


def _design_import(specifier, path, contract, stdlib, repository_roots):
    """Classify the existing collector's module[:member] syntax."""
    module, _, member = specifier.partition(":")
    source = _package(path[:-3].replace("/", "."), contract)
    if module.startswith("."):
        level = len(module) - len(module.lstrip("."))
        package = path.split("/")[:-1]
        if level > len(package):
            return "UNRESOLVED_RELATIVE", None
        suffix = module[level:]
        module = ".".join(package[:len(package) - level + 1]
                          + ([suffix] if suffix else []))
    parts = module.split(".")
    if not module or not all(part.isidentifier() for part in parts):
        return "UNRESOLVED_IMPORT", None
    if parts[0] == contract.package_root:
        if len(parts) == 1 and member.isidentifier():
            module += "." + member
        target = _package(module, contract)
        if target is None:
            return "UNRESOLVED_PACKAGE_ROOT", None
        return ("SAME_PACKAGE" if source == target else "CROSS_PACKAGE"), target
    if parts[0] in repository_roots or parts[0] == contract.repository_tool:
        return "REPOSITORY_DEPENDENCY", None
    if parts[0] in stdlib:
        return "STDLIB_CANDIDATE", None
    return "NON_STDLIB_OR_UNRESOLVED", None


def analyze_independent_dependencies(
    graph: GraphSnapshot, receipt: EvidenceReceipt, contract: DependencyContract,
    *, required_paths: tuple[str, ...], stdlib_modules: frozenset[str],
    repository_roots: frozenset[str],
) -> DependencyDesignReport:
    """Advisory design analysis; never called by the legacy CI verifier.

    Reuse PythonAstCollector import, call, dynamic and file reference edges. The
    caller supplies the exact inventory (including parent __init__.py where
    present) and target interpreter's standard-library names. Neither runtime
    imports nor standalone installation/extraction are proven by this report.
    Call and resource observations are lexical candidates; they do not prove
    external tool identity, actual access, or a violation. Aliases and indirect
    calls may evade lexical matching and need separate design review.
    """
    if not isinstance(contract, DependencyContract) or not contract.independent_packages:
        raise ValueError("INDEPENDENT_PACKAGE_CONTRACT_REQUIRED")
    if not isinstance(required_paths, tuple) or not required_paths or len(set(required_paths)) != len(required_paths):
        raise ValueError("EXACT_REQUIRED_PATHS_REQUIRED")
    for names in (stdlib_modules, repository_roots):
        if not isinstance(names, frozenset) or any(not isinstance(n, str) or not n.isidentifier() for n in names):
            raise ValueError("MODULE_NAME_INVENTORY_REQUIRED")
    if not stdlib_modules:
        raise ValueError("TARGET_STDLIB_INVENTORY_REQUIRED")
    from ..diagnostics.request import normalized_path
    root = contract.package_root + "/"
    parent_init = root + "__init__.py"
    for path in required_paths:
        normalized_path(path)
        if not path.startswith(root) or not path.endswith(".py") or (
            path != parent_init and _package(path[:-3].replace("/", "."), contract)
            not in contract.independent_packages
        ):
            raise ValueError("INDEPENDENT_SCOPE_PATH_INVALID")
    verification = verify_generated_artifact(graph, receipt)
    if verification.failures:
        raise ValueError("DEPENDENCY_EVIDENCE_INCONSISTENT:" + ",".join(verification.failures))
    coverage = {f.path: f for f in receipt.files}
    requested = set(required_paths)
    unknowns = set(graph.scope.unresolved) | set(receipt.unresolved)
    if graph.scope.completeness != "COMPLETE" or receipt.completeness != "COMPLETE":
        unknowns.add("INCOMPLETE_SCAN")
    for path in requested:
        item = coverage.get(path)
        if item is None or item.status != "SCANNED" or "python_ast" not in item.collectors:
            unknowns.add("SOURCE_NOT_FULLY_SCANNED:" + path)
    for path in coverage:
        if path == parent_init or (path.endswith(".py") and _package(path[:-3].replace("/", "."), contract) in contract.independent_packages):
            if path not in requested:
                unknowns.add("SOURCE_OUTSIDE_DECLARED_INVENTORY:" + path)
    for package in contract.independent_packages:
        if not any(p.startswith(root + package + "/") or p == root + package + ".py" for p in requested):
            unknowns.add("PACKAGE_INVENTORY_MISSING:" + package)
    nodes, evidence = graph.nodes_by_id(), graph.evidence_by_id()
    observations = set()
    findings = set()
    adjacency = {name: set() for name in contract.independent_packages}
    for edge in graph.edges:
        if edge.relation not in {"IMPORTS_CANDIDATE", "DYNAMIC_REFERENCE_CANDIDATE",
                                 "CALLS_CANDIDATE", "REFERENCES_FILE_CANDIDATE",
                                 "FILE_REFERENCE_UNRESOLVED", "REFERENCES_CANDIDATE"}:
            continue
        if not edge.evidence_ids:
            unknowns.add("DEPENDENCY_EVIDENCE_MISSING:" + edge.id)
        for eid in edge.evidence_ids:
            ev = evidence[eid]
            path = ev.attributes.get("path")
            if path not in requested:
                continue
            line, blob = ev.attributes.get("line"), ev.attributes.get("blob_sha")
            if type(line) is not int or line < 1 or path not in coverage or blob != coverage[path].blob_sha:
                unknowns.add("DEPENDENCY_WITNESS_INVALID:" + eid)
                continue
            source = _package(path[:-3].replace("/", "."), contract) or contract.package_root
            target = nodes[edge.target_id]
            if edge.relation == "DYNAMIC_REFERENCE_CANDIDATE":
                category, other = "DYNAMIC_UNRESOLVED", None
            elif edge.relation == "CALLS_CANDIDATE":
                callee = target.attributes.get("callee_expression", "")
                if not isinstance(callee, str):
                    unknowns.add("CALL_EXPRESSION_INVALID:" + eid)
                    continue
                # Lexical names only: no alias resolution or runtime assertion.
                if callee in {"subprocess.run", "subprocess.Popen", "subprocess.call",
                              "subprocess.check_call", "subprocess.check_output",
                              "os.system", "os.popen", "asyncio.create_subprocess_exec",
                              "asyncio.create_subprocess_shell"} or callee.startswith(
                                  ("os.exec", "os.spawn", "os.posix_spawn")):
                    category, other = "EXECUTION_CANDIDATE", None
                elif callee in {"open", "io.open", "os.open", "os.getenv",
                                "urllib.request.urlopen", "urlopen", "socket.create_connection"}:
                    category, other = "RESOURCE_ACCESS_CANDIDATE", None
                else:
                    continue
            elif edge.relation in {"REFERENCES_FILE_CANDIDATE", "FILE_REFERENCE_UNRESOLVED"}:
                category, other = ("RESOURCE_REFERENCE_CANDIDATE" if
                    edge.relation == "REFERENCES_FILE_CANDIDATE" else
                    "RESOURCE_REFERENCE_UNRESOLVED"), None
            elif edge.relation == "REFERENCES_CANDIDATE":
                if target.kind != "python_attribute_specifier" or target.name not in {
                    "os.environ", "os.environb", "sys.path", "sys.argv"
                }:
                    continue
                category, other = "RESOURCE_ACCESS_CANDIDATE", None
            elif target.kind != "python_import_specifier" or ev.observation_status != "SOURCE_DECLARED":
                category, other = "UNRESOLVED_IMPORT", None
            else:
                category, other = _design_import(target.name, path, contract, stdlib_modules, repository_roots)
            observations.add(DependencyObservation(category, path, line, source, target.name, blob, eid))
            if category == "CROSS_PACKAGE" and source in adjacency and other in adjacency:
                adjacency[source].add(other)
            if category in {"CROSS_PACKAGE", "REPOSITORY_DEPENDENCY", "NON_STDLIB_OR_UNRESOLVED"}:
                findings.add(DependencyFinding(category, path, line, source, target.name, blob,
                    "Independent packages may use only their own modules and the target standard library"))
            if category not in {"STDLIB_CANDIDATE", "SAME_PACKAGE", "CROSS_PACKAGE", "REPOSITORY_DEPENDENCY"}:
                unknowns.add(category + ":" + eid)
    cycle = _cycle(adjacency)
    status = ("DESIGN_VIOLATION_OBSERVED" if findings else
              "REVIEW_REQUIRED" if unknowns else "NO_STATIC_VIOLATION_OBSERVED")
    return DependencyDesignReport(receipt.revision, receipt.scope_id, status,
        tuple(sorted(observations, key=lambda f: (f.path, f.line, f.target, f.evidence_id))),
        tuple(sorted(findings, key=lambda f: (f.path, f.line, f.target, f.category))),
        cycle, tuple(sorted(unknowns)), tuple(sorted(requested)))


__all__ = [
    "ChangeVerificationPlan", "DependencyContract", "DependencyFinding",
    "DependencyRule", "DependencyVerification", "plan_change_verification",
    "verify_dependencies", "verify_dependency_repository",
    "DependencyObservation", "DependencyDesignReport", "analyze_independent_dependencies",
]
