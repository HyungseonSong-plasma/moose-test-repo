"""Zero-P3 Artifact CreateArtifact probe is a manual infrastructure diagnostic."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_probe_is_manual_and_never_scientific_p3():
    gen = (ROOT / "ci/workflow_templates/general-ci.yml").read_text()
    core = (ROOT / ".github/workflows/ci.yml").read_text()
    workflow = (ROOT / ".github/workflows/repository-diagnostics.yml").read_text()
    assert gen == core
    assert "  artifact-api-probe:\n" not in core
    assert "  artifact-api-probe:\n" in workflow
    assert "  workflow_dispatch:\n" in workflow
    assert "  pull_request:\n" not in workflow
    assert "  push:\n" not in workflow
    probe_tail = workflow.split("\n  artifact-api-probe:\n", 1)[1]
    section = re.split(r"\n  [A-Za-z_][A-Za-z0-9_-]*:\n", probe_tail, maxsplit=1)[0]
    assert "if-no-files-found: error" in section
    assert "actions/upload-artifact@v4" in section
    assert "retention-days: 1" in section
    assert "actions: read" in section
    assert "ISSUE518_ARTIFACT_CREATE_REST_VERIFIED" in section
    assert "run_canonical_s6_p3_once.py" not in section
    assert "make -C physics_app" not in section
    assert "docker" not in section
    assert "github.event.pull_request.number ==" not in section
