#!/usr/bin/env python3
"""Batch-6 guard for canonical model terminology and the single MOOSE boundary."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "qpx_harness"

FORBIDDEN_OWNER_PATHS = (
    HARNESS / "moose",
    HARNESS / "models",
    HARNESS / "ontology" / "model.py",
    HARNESS / "adapters" / "moose" / "mutation_spec" / "models.py",
)
FORBIDDEN_IMPORT_PREFIXES = (
    "qpx_harness.moose",
    "qpx_harness.models",
    "qpx_harness.ontology.model",
    "qpx_harness.adapters.moose.mutation_spec.models",
)
CANONICAL_MODEL_FIELD_FILES = {
    "qpx_harness/specification/schema.py",
    "qpx_harness/ontology/records.py",
    "qpx_harness/execution/plan.py",
    "qpx_harness/adapters/moose/target.py",
}


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _relative_import_base(path: Path, level: int, module: str | None) -> str:
    package = path.relative_to(ROOT).with_suffix("").parts[:-1]
    keep = max(0, len(package) - level + 1)
    base = ".".join(package[:keep])
    return ".".join(part for part in (base, module or "") if part)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    refs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            refs.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _relative_import_base(path, node.level, node.module) if node.level else (node.module or "")
            if base:
                refs.add(base)
            for alias in node.names:
                if alias.name != "*":
                    refs.add(".".join(part for part in (base, alias.name) if part))
    return refs


def _model_fields(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "model"
    )


def main() -> int:
    owner_residue = sorted(_rel(path) for path in FORBIDDEN_OWNER_PATHS if path.exists())
    import_edges: list[str] = []
    for path in sorted(HARNESS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for ref in sorted(_imports(path)):
            if any(ref == prefix or ref.startswith(prefix + ".") for prefix in FORBIDDEN_IMPORT_PREFIXES):
                import_edges.append(f"{_rel(path)} -> {ref}")

    ambiguous_fields: list[str] = []
    for rel in sorted(CANONICAL_MODEL_FIELD_FILES):
        path = ROOT / rel
        if not path.is_file():
            continue
        for line in _model_fields(path):
            ambiguous_fields.append(f"{rel}:{line}:model")

    print("CANONICAL_MOOSE_BOUNDARY=qpx_harness/adapters/moose")
    print("FORBIDDEN_OWNER_PATHS=" + repr(owner_residue))
    print("FORBIDDEN_IMPORT_EDGES=" + repr(import_edges))
    print("AMBIGUOUS_CANONICAL_MODEL_FIELDS=" + repr(ambiguous_fields))
    print(f"PUBLIC_MOOSE_INTEGRATION_BOUNDARY_COUNT={0 if (HARNESS / 'adapters' / 'moose').is_dir() is False else 1}")
    print(f"PARALLEL_MOOSE_ROOTS={1 if (HARNESS / 'moose').exists() else 0}")
    print(f"TOP_LEVEL_GENERIC_MODELS_PACKAGE={1 if (HARNESS / 'models').exists() else 0}")
    print(f"ONTOLOGY_RECORD_MODULES_NAMED_GENERIC_MODEL={1 if (HARNESS / 'ontology' / 'model.py').exists() else 0}")
    print(f"MUTATION_SCHEMA_MODULES_NAMED_GENERIC_MODELS={1 if (HARNESS / 'adapters' / 'moose' / 'mutation_spec' / 'models.py').exists() else 0}")

    ok = not owner_residue and not import_edges and not ambiguous_fields
    print("MODEL_TERMINOLOGY_AND_MOOSE_BOUNDARY_GUARD=" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
