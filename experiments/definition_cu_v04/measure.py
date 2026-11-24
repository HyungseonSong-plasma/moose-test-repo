"""Read-only v0.4 Definition CU audit over a bounded exact Git source inventory.

Uses the existing GitSourceProvider; never imports inspected modules or reads
worktree source as a substitute for Git HEAD. Name/README never inform role
inference. Lexical name probes are descriptive controls, NOT human CU ratings.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from libs.code_understandability.definition_metrics import (
    DefinitionClause, NameCue, measure_definition, profile_definition_context,
)
from physics_harness.code.analysis.definition_inference import (
    extract_behavior_witnesses, infer_from_behavior, BEHAVIOR_RULE_VERSION,
)

ROOT = "physics_harness/code"
TARGETS = ("graph", "diagnostics", "analysis", "refactor", "verification", "delete")
MAX_FILES_PER_TARGET = 50
MAX_BYTES_PER_TARGET = 1_000_000


def _under(path: str, folder: str) -> bool:
    return path.startswith(folder + "/") and path.endswith(".py") and "/tests/" not in path


def _public_cues(folder: str, source_records: tuple, provider) -> tuple[NameCue, ...]:
    """Build name disclosure cues from the same exact-blob inventory.

    All API labels are candidates, not proof of the owning declaration.
    Unsupported dynamic ``__all__`` is not silently replaced by guessed APIs.
    """
    import ast
    from pathlib import PurePosixPath
    cues = [NameCue("name", PurePosixPath(folder).name, 0, folder),
            NameCue("parent", PurePosixPath(folder).parent.name, 1,
                    PurePosixPath(folder).parent.as_posix())]
    for record in source_records:
        if PurePosixPath(record.path).parent.as_posix() == folder:
            stem = PurePosixPath(record.path).stem
            if stem != "__init__" and not stem.startswith("_"):
                cues.append(NameCue("module:" + stem, stem, 2, record.path + "@" + record.blob_sha))
    initializer = next((r for r in source_records if r.path == folder + "/__init__.py"), None)
    if initializer:
        content = provider.read(initializer)
        tree = ast.parse(content.decode("utf-8"), filename=initializer.path)
        for node in tree.body:
            assignment = node.value if isinstance(node, (ast.Assign, ast.AnnAssign)) else None
            if assignment is None:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                continue
            try:
                names = ast.literal_eval(assignment)
            except (TypeError, ValueError) as exc:
                raise ValueError("UNSUPPORTED_PUBLIC_CUES") from exc
            if not isinstance(names, (tuple, list)) or any(not isinstance(x, str) for x in names):
                raise ValueError("UNSUPPORTED_PUBLIC_CUES")
            for i, symbol in enumerate(names):
                cues.append(NameCue("api:" + str(i) + ":" + symbol, symbol, 3,
                                    f"{initializer.path}:{node.lineno}@{initializer.blob_sha}"))
    return tuple(cues)


def _contrast_name(clauses: tuple[DefinitionClause, ...], cues: tuple[NameCue, ...],
                   siblings: tuple[str, ...]) -> dict:
    """Matched sibling-name negative control; lexical only, not human behavior."""
    name = next(c for c in cues if c.tier == 0)
    parent = tuple(c for c in cues if c.tier == 1)

    def hits(candidate: str) -> int:
        pair = (NameCue("name", candidate, 0, name.source_ref),) + parent
        measured = measure_definition(clauses, pair)
        return measured.total_concepts - measured.definition_explanation_burden

    own = hits(name.text)
    competitors = tuple((other, hits(other)) for other in sorted(siblings) if other != name.text)
    winner = "LEXICALLY_DISTINCT" if competitors and own > max(h for _, h in competitors) else "NOT_LEXICALLY_DISTINCT"
    return {"criterion": "source_definition_vs_sibling_name_control",
            "observed_name_hits": own,
            "sibling_name_hits": [{"name": other, "hits": n} for other, n in competitors],
            "result": winner,
            "human_validation": False,
            "semantic_name_alignment_proven": False}



def _source_imports(path: str, source: str, blob_sha: str, owner: str) -> tuple[dict, ...]:
    """Source-only owner/consumer *candidates*, never resolved runtime imports."""
    import ast
    from pathlib import PurePosixPath

    tree = ast.parse(source, filename=path)
    parts = tuple(PurePosixPath(path).with_suffix("").parts[:-1])
    results = []
    for node in ast.walk(tree):
        modules: list[str] = []
        unresolved = False
        if isinstance(node, ast.Import):
            modules = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level - 1 > len(parts):
                    unresolved = True
                else:
                    base = parts[:len(parts) - node.level + 1] if node.level > 1 else parts
                    modules = [".".join(base + tuple(node.module.split(".")) if node.module else base)]
            else:
                modules = [node.module] if node.module else []
                unresolved = not modules
        else:
            continue
        for module in modules:
            suffix = module.removeprefix("physics_harness.code.")
            callee = suffix.split(".")[0] if suffix != module else None
            kind = ("WITHIN_OWNER_CANDIDATE" if callee == owner else
                    "CROSS_OWNER_CANDIDATE" if callee in TARGETS else
                    "OTHER_OR_UNRESOLVED_DEPENDENCY")
            results.append({"source_ref": f"{path}:{node.lineno}@{blob_sha}",
                            "module": module, "kind": kind})
        if unresolved:
            results.append({"source_ref": f"{path}:{node.lineno}@{blob_sha}",
                            "module": None, "kind": "UNRESOLVED_IMPORT"})
    return tuple(results)


def measure_from_provider(revision: str, provider, request) -> dict:
    """All tracked production .py in each selected folder, or explicit HOLD.

    ``provider.inventory(request)`` and ``provider.read(record)`` must be from
    the canonical exact-SHA GitSourceProvider; callers can inject a fixture
    provider in P0. No inference is promoted when the declared budget fails.
    """
    provider.assert_head(revision)
    records = provider.inventory(request)
    output = []
    for label in TARGETS:
        folder = ROOT + "/" + label
        selected = tuple(r for r in records if _under(r.path, folder))
        record_bytes = sum(r.size for r in selected)
        row = {"target": label, "folder": folder, "revision": revision,
               "tracked_python_files": len(selected), "source_bytes": record_bytes,
               "scanned_files": 0, "python_source_scope": "UNVERIFIED", "definition": None, "candidates": [],
               "definition_status": "UNRESOLVED", "unknowns": [],
               "metrics": None, "context_profile": None, "name_contrast": None,
               "source_evidence": [], "import_relations": [], "declared_entities": 0}
        if not selected:
            row["unknowns"] = ["NO_TRACKED_PYTHON_FILES"]
            output.append(row)
            continue
        if len(selected) > MAX_FILES_PER_TARGET or record_bytes > MAX_BYTES_PER_TARGET:
            row["unknowns"] = ["SOURCE_BUDGET_EXCEEDED"]
            output.append(row)
            continue
        scans = []
        imports = []
        declarations = 0
        for item in selected:
            if item.mode not in {"100644", "100755"}:
                row["unknowns"].append("NON_REGULAR_SOURCE:" + item.path)
                continue
            raw = provider.read(item)
            try:
                text = raw.decode("utf-8", "strict")
            except UnicodeDecodeError:
                row["unknowns"].append("SOURCE_ENCODING_UNSUPPORTED:" + item.path)
                continue
            scans.append(extract_behavior_witnesses(item.path, text, item.blob_sha, revision))
            imports.extend(_source_imports(item.path, text, item.blob_sha, label))
            import ast
            declarations += sum(isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                                for n in ast.walk(ast.parse(text, filename=item.path)))
        row["scanned_files"] = len(scans)
        row["python_source_scope"] = ("COMPLETE_TRACKED_PYTHON_ONLY"
                                      if len(scans) == len(selected) else "PARTIAL")
        row["import_relations"] = imports
        row["declared_entities"] = declarations
        finding = infer_from_behavior(tuple(scans), required_paths=tuple(r.path for r in selected))
        row["definition"] = finding.role
        row["candidates"] = list(finding.role_candidates)
        row["definition_status"] = finding.status
        row["unknowns"].extend(finding.unknowns)
        row["source_evidence"] = [{"kind": w.kind, "source_ref": w.source_ref,
                                   "observation": w.observation} for w in finding.evidence]
        if finding.clauses and row["python_source_scope"] == "COMPLETE_TRACKED_PYTHON_ONLY":
            cues = _public_cues(folder, selected, provider)
            numbers = measure_definition(finding.clauses, cues)
            profile = profile_definition_context(finding.clauses, cues)
            row["metrics"] = {
                "DEB": numbers.definition_explanation_burden,
                "DEB_denominator": numbers.total_concepts,
                "MRC_extra_cues": numbers.minimum_required_context,
                "MRC_tier": numbers.minimum_context_tier,
                "MRC_cues": list(numbers.selected_context_cues),
                "still_unrecoverable": list(numbers.still_unrecoverable)}
            row["context_profile"] = asdict(profile)
            row["name_contrast"] = _contrast_name(finding.clauses, cues, TARGETS)
        output.append(row)
    return {"schema_version": "0.4",
            "measurement_type": "bounded_full_tracked_python_source_ast_only",
            "exact_source_revision": revision,
            "source_provider": "GIT_TREE_EXACT_BLOB",
            "behavior_rule_version": BEHAVIOR_RULE_VERSION,
            "readme_used": False,
            "target_name_used_for_definition_inference": False,
            "semantic_cu_calibrated": False,
            "non_python_and_external_consumers_scanned": False,
            "results": output}


def measure_repository(root: Path, expected_revision: str | None = None) -> dict:
    from physics_harness.code.diagnostics import GitSourceProvider, ScanRequest

    provider = GitSourceProvider(root)
    revision = provider._git("rev-parse", "--verify", "HEAD").decode("ascii").strip()
    if expected_revision is not None and revision != expected_revision:
        raise ValueError("MEASUREMENT_REVISION_MISMATCH")
    request = ScanRequest(repository="HyungseonSong-plasma/moose-test-repo", revision=revision,
                          includes=(ROOT + "/**",), collectors=("python_ast",))
    return measure_from_provider(revision, provider, request)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--expected-revision")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = measure_repository(args.root, args.expected_revision)
    serialized = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
