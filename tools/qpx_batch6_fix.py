#!/usr/bin/env python3
"""One-shot stale-import sweep after the Batch-6 ownership migration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
replacements = [
    ("from . import model as semantic_model", "from . import records as semantic_model"),
    ("from .model import", "from .records import"),
    ("from ..ontology.model import", "from ..ontology.records import"),
    ("from ..models.stats import", "from ..evaluation.statistics import"),
    ("from .models import", "from .schema import"),
    ("from ..transforms import", "from qpx_harness.adapters.moose.transforms import"),
    ("from ..execution.regression import", "from qpx_harness.adapters.moose.regression import"),
    ("from ..petsc.options import", "from qpx_harness.adapters.moose.petsc_options import"),
    ("from ..moose.", "from qpx_harness.adapters.moose."),
]
changed = []
for base in (ROOT / "qpx_harness", ROOT / "tests", ROOT / "experiments", ROOT / "tools"):
    if not base.exists():
        continue
    for path in base.rglob("*.py"):
        if path.name == Path(__file__).name:
            continue
        text = path.read_text(encoding="utf-8")
        new = text
        for old, repl in replacements:
            new = new.replace(old, repl)
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed.append(path.relative_to(ROOT).as_posix())
print("BATCH6_STALE_IMPORT_SWEEP", changed)
