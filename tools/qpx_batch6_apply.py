#!/usr/bin/env python3
"""One-shot Batch-6 migration. The workflow removes this file after applying it."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
H = ROOT / "qpx_harness"
WF = ROOT / ".github/workflows/qpx-cleanup-validation.yml"


def move(src: str, dst: str) -> None:
    a, b = ROOT / src, ROOT / dst
    if not a.exists():
        return
    b.parent.mkdir(parents=True, exist_ok=True)
    if b.exists():
        raise RuntimeError(f"destination exists: {dst}")
    shutil.move(str(a), str(b))


def rewrite(path: Path, replacements: list[tuple[str, str]]) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    new = text
    for old, repl in replacements:
        new = new.replace(old, repl)
    if new != text:
        path.write_text(new, encoding="utf-8")


def all_text_files():
    for root in (H, ROOT / "tests", ROOT / "experiments", ROOT / "tools", ROOT / "docs"):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".md", ".json", ".txt"}:
                yield path


# Precise semantic-record and evaluation-contract owners.
move("qpx_harness/ontology/model.py", "qpx_harness/ontology/records.py")
move("qpx_harness/models/stats.py", "qpx_harness/evaluation/statistics.py")
models_init = H / "models/__init__.py"
if models_init.exists():
    models_init.unlink()
models_dir = H / "models"
if models_dir.exists() and not any(models_dir.iterdir()):
    models_dir.rmdir()
(H / "evaluation/__init__.py").write_text(
    '"""Normalized simulation evaluation data contracts."""\n'
    'from .statistics import *  # noqa: F401,F403\n', encoding="utf-8"
)

# Mutation schema records have a schema owner, not a generic models owner.
move(
    "qpx_harness/adapters/moose/mutation_spec/models.py",
    "qpx_harness/adapters/moose/mutation_spec/schema.py",
)

# Consolidate all concrete MOOSE mechanics under the one adapter boundary.
for name in (
    "blocks.py", "check_input.py", "dofmap.py", "executioner.py", "input.py",
    "log.py", "output_observation.py", "parameters.py", "preflight.py",
):
    move(f"qpx_harness/moose/{name}", f"qpx_harness/adapters/moose/{name}")
old_init = H / "moose/__init__.py"
if old_init.exists():
    old_init.unlink()
old_dir = H / "moose"
if old_dir.exists() and not any(old_dir.iterdir()):
    old_dir.rmdir()

# These surfaces are MOOSE-specific in implementation and therefore live at the boundary.
move("qpx_harness/transforms/registry.py", "qpx_harness/adapters/moose/transforms.py")
transforms_init = H / "transforms/__init__.py"
if transforms_init.exists():
    transforms_init.unlink()
transforms_dir = H / "transforms"
if transforms_dir.exists() and not any(transforms_dir.iterdir()):
    transforms_dir.rmdir()
move("qpx_harness/execution/regression.py", "qpx_harness/adapters/moose/regression.py")
move("qpx_harness/petsc/options.py", "qpx_harness/adapters/moose/petsc_options.py")

# Global ownership import migration, including tests and historical characterization code.
common = [
    ("qpx_harness.ontology.model", "qpx_harness.ontology.records"),
    ("qpx_harness.models.stats", "qpx_harness.evaluation.statistics"),
    ("qpx_harness.adapters.moose.mutation_spec.models", "qpx_harness.adapters.moose.mutation_spec.schema"),
    ("qpx_harness.execution.regression", "qpx_harness.adapters.moose.regression"),
    ("qpx_harness.petsc.options", "qpx_harness.adapters.moose.petsc_options"),
    ("qpx_harness.transforms", "qpx_harness.adapters.moose.transforms"),
    ("qpx_harness.moose.", "qpx_harness.adapters.moose."),
    ("qpx_harness.moose", "qpx_harness.adapters.moose"),
]
for path in list(all_text_files()):
    rewrite(path, common)

# Fix relative imports after physical moves.
rewrite(H / "adapters/moose/transforms.py", [
    ("from ..moose import blocks as moose_blocks", "from . import blocks as moose_blocks"),
    ("from ..moose import parameters as moose_parameters", "from . import parameters as moose_parameters"),
    ("from ..moose.input import MooseInput, MooseInputError", "from .input import MooseInput, MooseInputError"),
    ("from ..petsc import options as petsc_options", "from . import petsc_options"),
    ("from ..adapters.moose.mutation_spec.plan import", "from .mutation_spec.plan import"),
])
rewrite(H / "adapters/moose/regression.py", [
    ("from ..moose.preflight import", "from .preflight import"),
    ("from .reporting import", "from qpx_harness.execution.reporting import"),
    ("from .runtime import", "from qpx_harness.execution.runtime import"),
    ("from .status import", "from qpx_harness.execution.status import"),
    ("from .workspace import", "from qpx_harness.execution.workspace import"),
    ("from ..analysis.temporal import", "from qpx_harness.analysis.temporal import"),
])
rewrite(H / "adapters/moose/petsc_options.py", [
    ("from ..moose.parameters import", "from .parameters import"),
    ("from qpx_harness.adapters.moose.parameters import", "from .parameters import"),
])
# Relative imports internal to mutation spec and ontology.
for path in (H / "adapters/moose/mutation_spec").glob("*.py"):
    rewrite(path, [("from .models import", "from .schema import")])
for path in (H / "ontology").glob("*.py"):
    rewrite(path, [("from .model import", "from .records import")])

# Selected simulation model is one opaque reference term end-to-end.
model_files = [
    H / "specification/schema.py",
    H / "specification/compiler.py",
    H / "ontology/records.py",
    H / "planning/synthesizer.py",
    H / "execution/plan.py",
    H / "execution/compiler.py",
    H / "adapters/moose/target.py",
]
for path in model_files:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"\bmodel\b", "model_ref", text)
    path.write_text(text, encoding="utf-8")

# Migrate canonical schema-v2 fixture keys only; historical v1 remains immutable.
for path in (ROOT / "experiments").rglob("*.json"):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    if isinstance(data, dict) and data.get("schema_version") == 2 and "model" in data:
        if "model_ref" in data:
            raise RuntimeError(f"both model and model_ref in {path}")
        data["model_ref"] = data.pop("model")
        path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")

# Generic application no longer exposes concrete MOOSE preflight mechanics.
ops = H / "application/operations.py"
text = ops.read_text(encoding="utf-8")
text = re.sub(
    r"\n\ndef preflight_input\(path: str \| Path\) -> None:\n    from qpx_harness\.adapters\.moose\.preflight import validate_input_preflight\n\n    validate_input_preflight\(Path\(path\)\.expanduser\(\)\.resolve\(\)\)\n",
    "",
    text,
)
text = text.replace('    "preflight_input",\n', '')
ops.write_text(text, encoding="utf-8")
app_init = H / "application/__init__.py"
text = app_init.read_text(encoding="utf-8").replace("    preflight_input,\n", "").replace('    "preflight_input",\n', '')
app_init.write_text(text, encoding="utf-8")
cli = H / "cli/app.py"
text = cli.read_text(encoding="utf-8")
text = text.replace(
    "from qpx_harness.application import normalize_temporal_run_csv, preflight_input",
    "from qpx_harness.application import normalize_temporal_run_csv\nfrom qpx_harness.adapters.moose.preflight import validate_input_preflight",
)
text = text.replace("    preflight_input(args.input)", "    validate_input_preflight(Path(args.input).expanduser().resolve())")
text = text.replace('"test": "qpx_harness.adapters.moose.regression:cli_run_test"', '"test": "qpx_harness.adapters.moose.regression:cli_run_test"')
text = text.replace('"test-all": "qpx_harness.adapters.moose.regression:cli_run_all"', '"test-all": "qpx_harness.adapters.moose.regression:cli_run_all"')
# Ensure the new boundary guard runs in qpx -i architecture/all.
needle = '            [sys.executable, str(ROOT / "tools" / "qpx_numerical_method_ownership_guard.py")],\n'
if needle in text and "qpx_boundary_terminology_guard.py" not in text:
    text = text.replace(needle, needle + '            [sys.executable, str(ROOT / "tools" / "qpx_boundary_terminology_guard.py")],\n')
cli.write_text(text, encoding="utf-8")

# Concrete nonlinear runtime decoding belongs to adapter; generic evidence keeps only text-level signature extraction.
evidence_nl = H / "evidence/ingest/nonlinear_solver.py"
old = evidence_nl.read_text(encoding="utf-8")
head = old.split("\ndef measurement_failure_signature", 1)[0]
head = head.replace("import math\n", "").replace("from pathlib import Path\n", "").replace("from typing import Any, Iterable\n", "from typing import Any\n")
head = re.sub(r"\nfrom \.\.\.adapters\.moose import log as moose_log\nfrom \.\.\.petsc import log as petsc_log\nfrom \.termination import first_failed_reason\n", "\n", head)
head += '\n\n__all__ = ["FAILURE_PATTERNS", "failure_signature"]\n'
evidence_nl.write_text(head, encoding="utf-8")

adapter_nl = H / "adapters/moose/nonlinear_solver.py"
adapter_nl.write_text('''"""Concrete MOOSE/PETSc nonlinear runtime decoding at the solver boundary."""\nfrom __future__ import annotations\n\nimport math\nfrom pathlib import Path\nfrom typing import Any, Iterable, Mapping\n\nfrom . import log as moose_log\nfrom qpx_harness.petsc import log as petsc_log\nfrom qpx_harness.evidence.ingest.nonlinear_solver import failure_signature\nfrom qpx_harness.evidence.ingest.termination import first_failed_reason\n\n\ndef artifact_failure_signature(result: Mapping[str, Any] | None) -> dict[str, Any]:\n    if not result:\n        return {"signature": "NO_RESULT"}\n    evidence = result.get("evidence", {}) if isinstance(result, Mapping) else {}\n    log = None\n    if isinstance(evidence, Mapping):\n        preferred = ("runtime_log", "solver_log", "log")\n        values = [evidence.get(name) for name in preferred]\n        values.extend(value for key, value in evidence.items() if str(key).endswith("_log"))\n        for raw in values:\n            if isinstance(raw, str):\n                candidate = Path(raw)\n                if candidate.is_file():\n                    log = candidate\n                    break\n    text = log.read_text(errors="replace") if log else ""\n    facts = failure_signature(text)\n    facts["log"] = str(log) if log else None\n    return facts\n\n\ndef runtime_core_facts(text: str, *, returncode: int, coupled_scaling_variables: Iterable[str] = ()) -> dict[str, Any]:\n    residual_blocks = moose_log.parse_variable_residual_norms(text)\n    scaling_blocks = moose_log.parse_automatic_scaling_factors(text)\n    scaling = scaling_blocks[0] if scaling_blocks else {}\n    linear_reason = first_failed_reason(petsc_log.parse_linear_solve_terminations(text))\n    nonlinear_reason = first_failed_reason(petsc_log.parse_nonlinear_solve_terminations(text))\n    pc_failure_reason = petsc_log.parse_pc_failure_reason(text)\n    pc_hits = petsc_log.line_hits(text, (r"DIVERGED_PC_FAILED", r"DIVERGED_PCSETUP_FAILED", r"PC failed due to", r"zero pivot", r"factorization", r"PCSetUp.*fail"))\n    factorization_hits = petsc_log.line_hits(text, (r"FACTOR_(?:NUMERIC|STRUCT)_ZEROPIVOT", r"zero pivot", r"factorization", r"MatFactor", r"PCSetUp.*fail"))\n    nonfinite_residuals = [\n        {"block": index, "variable": name, "value": repr(value)}\n        for index, block in enumerate(residual_blocks) for name, value in block.items()\n        if not math.isfinite(value)\n    ]\n    requested = tuple(str(name) for name in coupled_scaling_variables)\n    scaling_invalid = [\n        {"variable": name, "value": repr(scaling[name])}\n        for name in requested if name in scaling and (not math.isfinite(scaling[name]) or scaling[name] == 0.0)\n    ]\n    selected = [abs(scaling[name]) for name in requested if name in scaling and math.isfinite(scaling[name]) and scaling[name] != 0.0]\n    ratio = max(selected) / min(selected) if len(selected) == 2 else None\n    return {\n        "returncode": returncode, "linear_reason": linear_reason, "nonlinear_reason": nonlinear_reason,\n        "pc_failure_reason": pc_failure_reason, "pc_hits": pc_hits, "factorization_hits": factorization_hits,\n        "variable_residuals": residual_blocks, "nonfinite_residuals": nonfinite_residuals,\n        "automatic_scaling_factors": scaling_blocks, "scaling_invalid": scaling_invalid,\n        "scaling_factor_ratio": ratio,\n    }\n\n__all__ = ["artifact_failure_signature", "runtime_core_facts"]\n''', encoding="utf-8")

# Remove concrete exports from generic evidence surface; callers must use adapter API.
for path in (H / "evidence/ingest/__init__.py", H / "evidence/__init__.py"):
    text = path.read_text(encoding="utf-8")
    text = text.replace("    measurement_failure_signature,\n", "").replace("    runtime_core_facts,\n", "")
    text = text.replace('    "measurement_failure_signature",\n', '').replace('    "runtime_core_facts",\n', '')
    path.write_text(text, encoding="utf-8")

# Rewrite known runtime decoder callers to the concrete adapter owner.
for path in list(all_text_files()):
    if path.suffix != ".py":
        continue
    text = path.read_text(encoding="utf-8")
    text = text.replace("measurement_failure_signature", "artifact_failure_signature")
    if "artifact_failure_signature" in text or "runtime_core_facts" in text:
        # Imports from evidence are migrated conservatively; tests reveal any unusual formatting.
        text = text.replace("from qpx_harness.evidence import artifact_failure_signature", "from qpx_harness.adapters.moose.nonlinear_solver import artifact_failure_signature")
        text = text.replace("from qpx_harness.evidence import runtime_core_facts", "from qpx_harness.adapters.moose.nonlinear_solver import runtime_core_facts")
        text = text.replace("from qpx_harness.evidence.ingest import artifact_failure_signature", "from qpx_harness.adapters.moose.nonlinear_solver import artifact_failure_signature")
        text = text.replace("from qpx_harness.evidence.ingest import runtime_core_facts", "from qpx_harness.adapters.moose.nonlinear_solver import runtime_core_facts")
    path.write_text(text, encoding="utf-8")

# Evaluation contracts become a recognized capability owner.
census = ROOT / "tools/qpx_architecture_census.py"
text = census.read_text(encoding="utf-8")
text = text.replace('    "models",\n', '').replace('    "moose",\n', '').replace('    "transforms",\n', '')
if '    "evaluation",\n' not in text:
    text = text.replace('    "evidence",\n', '    "evidence",\n    "evaluation",\n')
text = text.replace('    "moose",\n', '').replace('    "transforms",\n', '')
census.write_text(text, encoding="utf-8")
dep = ROOT / "tools/qpx_dependency_guard.py"
text = dep.read_text(encoding="utf-8")
text = text.replace('"evidence", "analysis", "execution", "application", "cli",', '"evidence", "evaluation", "analysis", "execution", "application", "cli",')
dep.write_text(text, encoding="utf-8")

# Boundary guard: allow no old owners/imports and require model_ref in canonical fields.
guard = ROOT / "tools/qpx_boundary_terminology_guard.py"
text = guard.read_text(encoding="utf-8")
text = text.replace('and node.target.id == "model"', 'and node.target.id == "model"')
guard.write_text(text, encoding="utf-8")

# Canonical ownership manifest.
manifest = ROOT / "docs/development/2026-09-06_batch6_model_moose_ownership.md"
manifest.write_text('''# Batch 6 canonical ownership manifest\n\n- Selected simulation-model reference term: `model_ref` end-to-end.\n- Canonical MOOSE integration boundary: `qpx_harness/adapters/moose/`.\n- Semantic lowering: `adapters/moose/target.py`.\n- HIT syntax/parser/render primitives: `adapters/moose/input.py`, `blocks.py`, `parameters.py`.\n- Declarative mutation schema/application: `adapters/moose/mutation_spec/` and `adapters/moose/transforms.py`.\n- Runtime/preflight/regression: `adapters/moose/preflight.py`, `regression.py`, `executioner.py`, `dofmap.py`.\n- MOOSE log/output decoding: `adapters/moose/log.py`, `nonlinear_solver.py`, `output_observation.py`.\n- MOOSE-specific PETSc option mutation: `adapters/moose/petsc_options.py`. Pure PETSc diagnostic parsers remain under `qpx_harness/petsc/`.\n- Normalized run/evaluation contracts: `qpx_harness/evaluation/statistics.py`.\n- Semantic ontology records: `qpx_harness/ontology/records.py`.\n- MOOSE mutation-spec records: `qpx_harness/adapters/moose/mutation_spec/schema.py`.\n\nAllowed direction: semantic specification/planning/execution IR -> public MOOSE adapter -> concrete solver syntax/runtime -> decoded observations/evidence. Generic evidence/analysis/reasoning must not import concrete MOOSE mechanics. Exact MOOSE/QPX/PETSc identifiers remain valid only where they represent external contracts.\n''', encoding="utf-8")

# Remove one-shot tooling and temporary workflow write block. The final pushed tree is read-only again.
workflow = WF.read_text(encoding="utf-8")
start = "      # BATCH6_APPLY_START\n"
end = "      # BATCH6_APPLY_END\n"
if start in workflow and end in workflow:
    a = workflow.index(start)
    b = workflow.index(end, a) + len(end)
    workflow = workflow[:a] + workflow[b:]
workflow = workflow.replace("permissions:\n  contents: write\n\n", "")
WF.write_text(workflow, encoding="utf-8")
Path(__file__).unlink()
print("BATCH6_MIGRATION_APPLIED")
