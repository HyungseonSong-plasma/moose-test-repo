"""Compute bounded, read-only behavior Definition / DEB / MRC from a real checkout.

Only sampled Python files are considered; NEVER call this full-folder
coverage, runtime behavior, documentation redundancy or safe deletion.
"""
from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path
import subprocess

from libs.code_understandability.definition_metrics import measure_definition
from physics_harness.code.analysis.definition_inference import (
    extract_behavior_witnesses, infer_from_behavior,
    extract_public_symbols_from_folder, make_folder_cues,
)

TARGETS = (
    ("graph", "physics_harness/code/graph/edge.py"),
    ("diagnostics", "physics_harness/code/diagnostics/providers/python_ast.py"),
    ("analysis", "physics_harness/code/analysis/impact.py"),
    ("refactor", "physics_harness/code/refactor/alternatives.py"),
    ("verification", "physics_harness/code/verification/consistency.py"),
    ("delete", "physics_harness/code/delete/__init__.py"),
)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def public_module_cues(folder: Path) -> tuple[str, ...]:
    """Only public, direct Python modules; private plumbing is not default CU context."""
    return tuple(sorted(p.stem for p in folder.glob("*.py")
                        if p.name != "__init__.py" and not p.stem.startswith("_")))


def measure_repository(root: Path, *, expected_revision: str | None = None) -> dict:
    root = root.resolve()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if expected_revision is not None and revision != expected_revision:
        raise ValueError("MEASUREMENT_REVISION_MISMATCH")
    results = []
    for label, path in TARGETS:
        source_path = root / path
        content = source_path.read_bytes()
        blob_sha = git_blob(content)
        # The byte identity is verified once more inside the AST extractor.
        scan = extract_behavior_witnesses(path, content.decode("utf-8"), blob_sha, revision)
        inferred = infer_from_behavior((scan,), required_paths=(path,))
        folder = "physics_harness/code/" + label  # public package, not nested sample provider
        result = {
            "target": label,
            "target_kind": "FOLDER_SAMPLE_FROM_PYTHON_FILE",
            "sample_path": path,
            "sample_blob": blob_sha,
            "source_revision": revision,
            "definition": inferred.role,
            "definition_status": inferred.status,
            "unknowns": inferred.unknowns,
            "witnesses": [
                {"kind": w.kind, "source_ref": w.source_ref,
                 "observation": w.observation} for w in inferred.evidence
            ],
            "metrics": None,
        }
        if inferred.clauses:
            symbols = extract_public_symbols_from_folder(root, folder)
            direct = public_module_cues(root / folder)
            cues = make_folder_cues(folder, symbols, direct)
            numbers = measure_definition(inferred.clauses, cues)
            result["metrics"] = {
                "DEB": numbers.definition_explanation_burden,
                "DEB_denominator": numbers.total_concepts,
                "DEB_fraction": numbers.explanation_burden_fraction,
                "MRC_extra_cues": numbers.minimum_required_context,
                "MRC_tier": numbers.minimum_context_tier,
                "MRC_cues": numbers.selected_context_cues,
                "unpredicted_baseline": numbers.unpredicted_concepts,
                "not_recoverable_in_scope": numbers.still_unrecoverable,
            }
        results.append(result)
    return {
        "schema_version": "0.3",
        "measurement_type": "partial_static_ast_behavior_evidence",
        "exact_checkout_sha": revision,
        "readme_used": False,
        "target_name_used_for_definition_inference": False,
        "scope_complete_for_whole_folder": False,
        "human_cu_calibrated": False,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--expected-revision")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = measure_repository(args.root, expected_revision=args.expected_revision)
    serialized = json.dumps(results, indent=2, ensure_ascii=False) + "\n"
    if args.output is None:
        print(serialized, end="")
    else:
        args.output.write_text(serialized, encoding="utf-8")


if __name__ == "__main__":
    main()
