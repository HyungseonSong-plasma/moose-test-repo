"""Real repository: candidate-blind stable collector baseline, without semantic PASS."""
from __future__ import annotations

from pathlib import Path
import subprocess

from physics_harness.code.diagnostics.providers.git import GitSourceProvider
from physics_harness.code.refactor.naming import NamingCase, NamingEvidence
from physics_harness.code.verification.naming_boundary import ResponsibilityBinding
from physics_harness.code.verification.naming_semantic_review import build_blinded_semantic_packet

ROOT = Path(__file__).resolve().parents[3]
TARGET = "physics_harness/code/diagnostics/collector.py"


def test_real_collector_blinded_review_packet_has_immutable_witnesses():
    revision = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT, text=True).strip()
    provider = GitSourceProvider(ROOT)
    src = provider.read_at_revision(revision, TARGET)
    lines = src.content.decode("utf-8").splitlines()
    def ref(prefix):
        loc = [i for i, text in enumerate(lines, 1) if text.startswith(prefix)]
        assert len(loc) == 1
        return f"{TARGET}:{loc[0]}@{src.record.blob_sha}"
    responsibilities = (
        NamingEvidence("contract", "RESPONSIBILITY", "Collector interface",
                       (ref("class Collector("),), revision),
        NamingEvidence("entry", "RESPONSIBILITY", "Orchestrate source scanning",
                       (ref("def run_scan("),), revision),
    )
    case = NamingCase("HyungseonSong-plasma/moose-test-repo", revision,
        "FILE", "existing-collector", "collector", TARGET, ("contract", "entry"),
        responsibilities, "RESOLVED", "COHERENT", "VALID")
    bindings = (
        ResponsibilityBinding("contract", (TARGET+"::class:Collector",)),
        ResponsibilityBinding("entry", (TARGET+"::function:run_scan",)),
    )
    packet = build_blinded_semantic_packet(case, provider, bindings,
                                            max_symbol_chars=100000)
    assert len(packet.observed_symbol_keys) >= 2
    assert any("::class:Collector" in s for s in packet.observed_symbol_keys)
    assert any("def run_scan(" in s.code for s in packet.excerpts)
    assert packet.revision == revision
    assert not packet.mutation_approved
