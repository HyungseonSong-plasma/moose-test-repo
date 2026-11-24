"""P6-C3 source-only regression for CI/Template Trigger/Artifact/P05 safety.

No CI dispatch, Native binary, high-cost solver, protected source, or P3/P4.
"""
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
G = runpy.run_path(str(ROOT / "ci/guards/p6_ci_workflow_safety_guard.py"))


def _sources():
    return (
        (ROOT / ".github/workflows/ci.yml").read_text(),
        (ROOT / "ci/workflow_templates/general-ci.yml").read_text(),
        (ROOT / "physics_app/src/physics/plasma/DDContinuityEq.C").read_text(),
    )


def test_p6_ci_trigger_artifact_p05_source_contract():
    G["validate"](*_sources())


def test_p6_ci_mutations_fail_closed():
    assert G["self_test"](*_sources()) == 32
