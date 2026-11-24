"""Actual tracked-Git current-source KEEP negative control (semantic claim is manual)."""
from __future__ import annotations

from pathlib import Path
import subprocess

from physics_harness.code.diagnostics.providers.git import GitSourceProvider
from physics_harness.code.refactor.naming import (
    NamingCase, NamingEvidence, NamingOption, NamingRecommendation,
    RejectedNamingCandidate, adjudicate_naming_recommendation,
)

ROOT = Path(__file__).resolve().parents[3]
FILE = "physics_harness/code/diagnostics/collector.py"


def test_actual_collector_context_preserves_stable_general_name():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                   cwd=ROOT, text=True).strip()
    provider = GitSourceProvider(ROOT)
    original = provider.read_at_revision(head, FILE)
    content = original.content.decode("utf-8").splitlines()
    blob = original.record.blob_sha

    def source_ref(fragment: str) -> str:
        matches = [i + 1 for i, line in enumerate(content) if fragment in line]
        assert len(matches) == 1, (fragment, matches)
        return f"{FILE}:{matches[0]}@{blob}"

    facts = (
        NamingEvidence("collector", "RESPONSIBILITY", "Declares abstract collector contract",
                       (source_ref("class Collector(Protocol):"),), head),
        NamingEvidence("run_scan", "RESPONSIBILITY", "Coordinates supported collectors",
                       (source_ref("def run_scan("),), head),
        NamingEvidence("python", "CONTEXT", "Existing Python implementation is delegated",
                       (source_ref("from .providers.python_ast import PythonAstCollector"),), head),
        NamingEvidence("cpp", "CONTEXT", "Existing C++ implementation is delegated",
                       (source_ref("from .providers.cpp import CppSourceCollector"),), head),
    )
    # These role and name-fit claims are manually reviewed hypotheses, not
    # proved by the line anchor: the provenance verifier validates only bytes.
    case = NamingCase("HyungseonSong-plasma/moose-test-repo", head, "FILE",
                      "collector-owner", "collector", FILE,
                      ("collector", "run_scan"), facts, "RESOLVED",
                      "COHERENT", "VALID")
    keep = NamingOption("keep", "KEEP", "Retain generic interface and owner")
    proposal = NamingOption("rename", "RENAME", "Specific interface name",
                            proposed_name="python_cpp_collector",
                            retained_responsibility_ids=("collector", "run_scan"),
                            impact_paths=(FILE,))
    suggestion = NamingRecommendation(
        "keep", "", (),
        (RejectedNamingCandidate("rename", "Already general; specific name loses boundary",
                                 ("collector", "python", "cpp")),),
        "Prefer the stable generic responsibility name")
    decision = adjudicate_naming_recommendation(case, (keep, proposal), suggestion, provider)
    assert decision.disposition == "KEEP"
    assert decision.provenance == "SOURCE_ANCHORS_VERIFIED"
    assert decision.recommended_option_id == "keep"
    assert decision.required_checks == ()
    assert not decision.mutation_approved
