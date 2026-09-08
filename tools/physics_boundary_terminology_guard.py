#!/usr/bin/env python3
"""Canonical model terminology and single-MOOSE-boundary architecture guard."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "physics_harness"

RETIRED_OWNER_PATHS = (
    HARNESS / "moose",
    HARNESS / "models",
    HARNESS / "ontology" / "model.py",
    HARNESS / "adapters" / "moose" / "mutation_spec" / "models.py",
)
RETIRED_IMPORT_PREFIXES = (
    "physics_harness.moose",
    "physics_harness.models",
    "physics_harness.ontology.model",
    "physics_harness.adapters.moose.mutation_spec.models",
)
CONCRETE_MOOSE_PREFIXES = (
    "physics_harness.adapters.moose.input",
    "physics_harness.adapters.moose.blocks",
    "physics_harness.adapters.moose.parameters",
    "physics_harness.adapters.moose.preflight",
    "physics_harness.adapters.moose.log",
    "physics_harness.adapters.moose.nonlinear_solver",
    "physics_harness.adapters.moose.output_observation",
    "physics_harness.adapters.moose.petsc_options",
    "physics_harness.adapters.moose.transforms",
    "physics_harness.adapters.moose.regression",
)
CANONICAL_MODEL_FIELD_FILES = (
    "physics_harness/specification/schema.py",
    "physics_harness/ontology/records.py",
    "physics_harness/execution/plan.py",
    "physics_harness/adapters/moose/target.py",
)
EXPLICIT_CONCRETE_PRESENTATION_EXEMPTIONS = {
    "physics_harness/cli/app.py": {"physics_harness.adapters.moose.preflight"},
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


def _matches(ref: str, prefixes: tuple[str, ...]) -> bool:
    return any(ref == prefix or ref.startswith(prefix + ".") for prefix in prefixes)


def _field_lines(path: Path, field_name: str) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == field_name
    )


def main() -> int:
    retired_paths = sorted(_rel(path) for path in RETIRED_OWNER_PATHS if path.exists())
    retired_edges: list[str] = []
    concrete_edges: list[str] = []
    evidence_solver_edges: list[str] = []

    for path in sorted(HARNESS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = _rel(path)
        inside_moose_boundary = rel.startswith("physics_harness/adapters/moose/")
        exemptions = EXPLICIT_CONCRETE_PRESENTATION_EXEMPTIONS.get(rel, set())
        for ref in sorted(_imports(path)):
            if _matches(ref, RETIRED_IMPORT_PREFIXES):
                retired_edges.append(f"{rel} -> {ref}")
            if _matches(ref, CONCRETE_MOOSE_PREFIXES) and not inside_moose_boundary:
                if not any(ref == allowed or ref.startswith(allowed + ".") for allowed in exemptions):
                    concrete_edges.append(f"{rel} -> {ref}")
                    if rel.startswith("physics_harness/evidence/"):
                        evidence_solver_edges.append(f"{rel} -> {ref}")

    ambiguous_fields: list[str] = []
    missing_model_ref: list[str] = []
    for rel in CANONICAL_MODEL_FIELD_FILES:
        path = ROOT / rel
        if not path.is_file():
            missing_model_ref.append(rel + ":MISSING")
            continue
        for line in _field_lines(path, "model"):
            ambiguous_fields.append(f"{rel}:{line}:model")
        if "model_ref" not in path.read_text(encoding="utf-8"):
            missing_model_ref.append(rel)

    evidence_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted((HARNESS / "evidence").rglob("*.py"))
    )
    pf_keys = sorted(key for key in ("p2_log", "p3_log") if key in evidence_text)

    adapter = HARNESS / "adapters" / "moose"
    public_boundary_count = 1 if adapter.is_dir() else 0
    input_owner_count = 1 if (adapter / "target.py").is_file() and (adapter / "input.py").is_file() else 0
    mutation_owner_count = 1 if (adapter / "transforms.py").is_file() and (adapter / "mutation_spec").is_dir() else 0
    output_owner_count = 1 if (adapter / "output_observation.py").is_file() else 0

    model_ok = not ambiguous_fields and not missing_model_ref
    moose_ok = (
        public_boundary_count == 1
        and not (HARNESS / "moose").exists()
        and not retired_edges
        and not concrete_edges
        and input_owner_count == 1
        and mutation_owner_count == 1
        and output_owner_count == 1
    )
    ok = model_ok and moose_ok and not retired_paths and not pf_keys and not evidence_solver_edges

    print("CANONICAL_SELECTED_MODEL_TERM=model_ref")
    print(f"CANONICAL_SELECTED_MODEL_TERM_COUNT={1 if model_ok else 0}")
    print("AMBIGUOUS_MODEL_FIELDS_IN_CONTROL_PLANE=" + str(len(ambiguous_fields)))
    print("MISSING_MODEL_REF_OWNERS=" + repr(missing_model_ref))
    print("CROSS_LAYER_MODEL_TERM_SEMANTICS=" + ("UNAMBIGUOUS" if model_ok else "FAIL"))
    print("RETIRED_OWNER_PATHS=" + repr(retired_paths))
    print("RETIRED_OWNER_IMPORT_EDGES=" + repr(retired_edges))
    print("GENERIC_TO_MOOSE_CONCRETE_DEPENDENCY_EDGES=" + str(len(concrete_edges)))
    print("GENERIC_TO_MOOSE_CONCRETE_DEPENDENCY_EDGE_LIST=" + repr(concrete_edges))
    print("GENERIC_EVIDENCE_TO_CONCRETE_SOLVER_LOG_DECODING_EDGES=" + str(len(evidence_solver_edges)))
    print("PF_CAMPAIGN_KEYS_IN_GENERIC_EVIDENCE=" + str(len(pf_keys)))
    print(f"PUBLIC_MOOSE_INTEGRATION_BOUNDARY_COUNT={public_boundary_count}")
    print(f"PARALLEL_MOOSE_ROOTS={1 if (HARNESS / 'moose').exists() else 0}")
    print(f"MOOSE_INPUT_REALIZATION_OWNER_COUNT={input_owner_count}")
    print(f"MOOSE_SYNTAX_MUTATION_OWNER_COUNT={mutation_owner_count}")
    print(f"MOOSE_OUTPUT_DECODER_OWNER_COUNT={output_owner_count}")
    print(f"TOP_LEVEL_GENERIC_MODELS_PACKAGE={1 if (HARNESS / 'models').exists() else 0}")
    print(f"ONTOLOGY_RECORD_MODULES_NAMED_GENERIC_MODEL={1 if (HARNESS / 'ontology' / 'model.py').exists() else 0}")
    print(f"MUTATION_SCHEMA_MODULES_NAMED_GENERIC_MODELS={1 if (adapter / 'mutation_spec' / 'models.py').exists() else 0}")
    print("MODEL_TERMINOLOGY_GUARD=" + ("PASS" if model_ok and not retired_paths and not retired_edges else "FAIL"))
    print("MOOSE_ADAPTER_BOUNDARY_GUARD=" + ("PASS" if moose_ok else "FAIL"))
    print("MODEL_TERMINOLOGY_AND_MOOSE_BOUNDARY_GUARD=" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
