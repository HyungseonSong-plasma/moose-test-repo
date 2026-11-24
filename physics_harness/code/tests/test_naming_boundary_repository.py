"""Real exact-HEAD stable collector ownership: structural control, not semantic proof."""
from __future__ import annotations

from pathlib import Path
import subprocess

from physics_harness.code.diagnostics.providers.git import GitSourceProvider
from physics_harness.code.refactor.naming import NamingCase, NamingEvidence, NamingOption
from physics_harness.code.verification.naming_boundary import (
    ResponsibilityBinding, verify_naming_boundary,
)

ROOT = Path(__file__).resolve().parents[3]
FILE = "physics_harness/code/diagnostics/collector.py"


def test_real_generic_collector_boundary_is_kept():
    head = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT, text=True).strip()
    provider = GitSourceProvider(ROOT)
    source = provider.read_at_revision(head, FILE)
    lines = source.content.decode("utf-8").splitlines()
    blob = source.record.blob_sha

    def citation(prefix):
        exact = [i for i, line in enumerate(lines, 1) if line.startswith(prefix)]
        assert len(exact) == 1, (prefix, exact)
        return f"{FILE}:{exact[0]}@{blob}"

    declared = (
        NamingEvidence("owner", "RESPONSIBILITY", "Collector contract",
                       (citation("class Collector("),), head),
        NamingEvidence("scan", "RESPONSIBILITY", "Common scan orchestration entrypoint",
                       (citation("def run_scan("),), head),
    )
    case = NamingCase("HyungseonSong-plasma/moose-test-repo", head, "FILE",
        "collector-owner", "collector", FILE, ("owner", "scan"), declared,
        "RESOLVED", "COHERENT", "VALID")
    bindings = (
        ResponsibilityBinding("owner", (FILE+"::class:Collector",)),
        ResponsibilityBinding("scan", (FILE+"::function:run_scan",)),
    )
    receipt = verify_naming_boundary(case,
             NamingOption("keep", "KEEP", "Common collector name spans existing providers"),
             provider, bindings)
    assert receipt.status == "STRUCTURE_WITNESSED"
    assert len(receipt.verified_bindings) == 2
    assert not receipt.semantic_compatibility_proven
    assert not receipt.mutation_approved
