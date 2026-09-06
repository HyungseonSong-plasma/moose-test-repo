#!/usr/bin/env python3
"""One-shot stale-import sweep after the Batch-6 ownership migration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"qpx_batch6_fix.py", "qpx_boundary_terminology_guard.py"}
replacements = [
    ("qpx_harness.models.stats", "qpx_harness.evaluation.statistics"),
    ("qpx_harness.ontology.model", "qpx_harness.ontology.records"),
    ("qpx_harness.adapters.moose.mutation_spec.models", "qpx_harness.adapters.moose.mutation_spec.schema"),
    ("qpx_harness.execution.regression", "qpx_harness.adapters.moose.regression"),
    ("qpx_harness.petsc.options", "qpx_harness.adapters.moose.petsc_options"),
    ("qpx_harness.transforms", "qpx_harness.adapters.moose.transforms"),
    ("qpx_harness.moose.", "qpx_harness.adapters.moose."),
    ("from . import model as semantic_model", "from . import records as semantic_model"),
    ("from .model import", "from .records import"),
    ("from ...models.stats import", "from ...evaluation.statistics import"),
    ("from ..models.stats import", "from ..evaluation.statistics import"),
    ("from .models import", "from .schema import"),
]
changed = []
for base in (ROOT / "qpx_harness", ROOT / "tests", ROOT / "experiments", ROOT / "tools"):
    if not base.exists():
        continue
    for path in base.rglob("*.py"):
        if path.name in SKIP:
            continue
        text = path.read_text(encoding="utf-8")
        new = text
        for old, repl in replacements:
            new = new.replace(old, repl)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed.append(path.relative_to(ROOT).as_posix())
print("BATCH6_STALE_IMPORT_SWEEP", changed)
