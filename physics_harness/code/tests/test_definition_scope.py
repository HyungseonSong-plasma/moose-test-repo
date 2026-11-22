"""v0.4 source scope and cue counterfactual controls; no execution of target code."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1

import pytest

from libs.code_understandability.definition_metrics import (
    DefinitionClause, NameCue, measure_definition, profile_definition_context,
)
from experiments.definition_cu_v04.measure import (
    TARGETS, _contrast_name, _public_cues, measure_from_provider,
)

REV = "a" * 40


def blob(data: bytes) -> str:
    return sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


@dataclass(frozen=True)
class Record:
    path: str
    size: int
    blob_sha: str
    mode: str = "100644"


class FakeGitObjects:
    def __init__(self, files: dict[str, str], revision: str = REV):
        self.bytes = {p: s.encode("utf-8") for p, s in files.items()}
        self.records = tuple(Record(p, len(raw), blob(raw))
                             for p, raw in sorted(self.bytes.items()))
        self.revision = revision
        self.reads = []

    def assert_head(self, revision):
        if revision != self.revision:
            raise ValueError("GIT_HEAD_MISMATCH")

    def inventory(self, request):
        return self.records

    def read(self, record):
        self.reads.append(record.path)
        return self.bytes[record.path]


def test_tier_profile_respects_contextual_short_names():
    c = (DefinitionClause("node", ("a.py:1@sha",)),
         DefinitionClause("edge", ("a.py:2@sha",)),
         DefinitionClause("parse", ("a.py:3@sha",)))
    cues = (NameCue("name", "map", 0, "target"),
            NameCue("parent", "graph", 1, "parent"),
            NameCue("module:parser", "parse", 2, "parser.py"))
    profile = profile_definition_context(c, cues)
    assert profile.tiers[0].covered == ()
    assert profile.tiers[1].gained == ("node", "edge")
    assert profile.tiers[2].gained == ("parse",)
    assert profile.tiers[3].gained == ()
    assert measure_definition(c, cues).minimum_required_context == 1


def test_name_contrast_reports_only_lexical_discriminability():
    clauses = (DefinitionClause("verify", ("a.py:2@sha",)),)
    cues = (NameCue("name", "verification", 0, "p"),
            NameCue("parent", "code", 1, "p"))
    result = _contrast_name(clauses, cues, ("verification", "analysis", "refactor"))
    assert result["result"] == "LEXICALLY_DISTINCT"
    assert result["semantic_name_alignment_proven"] is False
    ambiguous = _contrast_name(clauses, (NameCue("name", "mystery", 0, "p"), cues[1]),
                               ("mystery", "analysis", "refactor"))
    assert ambiguous["result"] == "NOT_LEXICALLY_DISTINCT"


def test_exact_inventory_scans_production_files_not_tests_or_readmes():
    f = "physics_harness/code/graph/"
    files = {
        f + "edge.py": "from dataclasses import dataclass\n@dataclass(frozen=True)\nclass R:\n  source_id: str\n  target_id: str\n",
        f + "node.py": "from dataclasses import dataclass\n@dataclass(frozen=True)\nclass N:\n  subject_refs: tuple\n  evidence_refs: tuple\n",
        f + "__init__.py": '__all__ = ["Node", "Edge"]\n',
        f + "tests/test_inside.py": "assert False\n",
        f + "README.md": "This should never be read.",
        "physics_harness/code/delete/__init__.py": '__all__ = []\n',
    }
    provider = FakeGitObjects(files)
    result = measure_from_provider(REV, provider, object())
    assert result["readme_used"] is False
    assert result["source_provider"] == "GIT_TREE_EXACT_BLOB"
    graph = next(x for x in result["results"] if x["target"] == "graph")
    assert graph["tracked_python_files"] == 3
    assert graph["scanned_files"] == 3
    assert graph["definition"] == "GRAPH_MODEL"
    assert graph["definition_status"] == "CANDIDATE_WITHIN_SCOPE"
    assert graph["metrics"] is not None
    assert graph["context_profile"] is not None
    assert graph["name_contrast"]["human_validation"] is False
    assert "README.md" not in "|".join(provider.reads)
    assert "test_inside.py" not in "|".join(provider.reads)
    assert all(w["source_ref"].split("@")[-1] in {r.blob_sha for r in provider.records}
               for w in graph["source_evidence"])


def test_wrong_git_object_identity_fails_closed():
    p = "physics_harness/code/graph/edge.py"
    provider = FakeGitObjects({p: "x=1\n"})
    record = provider.records[0]
    provider.records = (Record(record.path, record.size, "b" * 40),)
    with pytest.raises(ValueError, match="BLOB_MISMATCH"):
        measure_from_provider(REV, provider, object())


def test_unrelated_or_unsupported_scope_not_claimed_complete():
    provider = FakeGitObjects({"other/module.py": "x=1\n"})
    o = measure_from_provider(REV, provider, object())
    assert all(x["definition"] is None for x in o["results"])
    assert all(x["unknowns"] == ["NO_TRACKED_PYTHON_FILES"] for x in o["results"])


def test_bad_expected_head_fails_before_reads():
    provider = FakeGitObjects({"physics_harness/code/graph/edge.py": "x=1\n"})
    with pytest.raises(ValueError, match="HEAD_MISMATCH"):
        measure_from_provider("b" * 40, provider, object())
    assert provider.reads == []


def test_ambiguous_full_folder_refuses_universal_definition():
    prefix = "physics_harness/code/analysis/"
    provider = FakeGitObjects({
        prefix+"model.py": "from dataclasses import dataclass\n@dataclass(frozen=True)\nclass R:\n  source_id: str\n  target_id: str\n",
        prefix+"impact.py": "def f(g,c):\n  view=unfold_context(g,c)\n  return ImpactResult(view=view)\n",
    })
    report = measure_from_provider(REV, provider, object())
    analysis = next(x for x in report["results"] if x["target"] == "analysis")
    assert analysis["definition"] is None
    assert "MULTIPLE_BEHAVIOR_ROLES" in analysis["unknowns"]
    assert analysis["metrics"] is None


def test_private_and_nested_modules_are_not_default_cues():
    prefix = "physics_harness/code/analysis/"
    provider = FakeGitObjects({
        prefix + "__init__.py": '__all__ = ["run"]\n',
        prefix + "public.py": "def run(): return 1\n",
        prefix + "_private.py": "def impl(): return 1\n",
        prefix + "nested/internal.py": "def hidden(): return 1\n",
    })
    cues = _public_cues(prefix.rstrip("/"), provider.records, provider)
    labels = {c.label for c in cues}
    assert "module:public" in labels
    assert "module:_private" not in labels
    assert "module:internal" not in labels
    assert "api:0:run" in labels


def test_exported_api_claim_is_not_automatic_ownership():
    prefix = "physics_harness/code/analysis/"
    provider = FakeGitObjects({prefix+"__init__.py": '__all__ = ["ExternalThing"]\n'})
    cues = _public_cues(prefix.rstrip("/"), provider.records, provider)
    assert next(x for x in cues if x.tier == 3).text == "ExternalThing"
    assert all("IMPLEMENTED_OWNER" not in c.source_ref for c in cues)


def test_cross_folder_usage_not_mistaken_for_owned_declaration():
    from experiments.definition_cu_v04.measure import _source_imports
    text = "from ..graph import Node\nfrom .local import fn\nimport json\n"
    refs = _source_imports("physics_harness/code/analysis/impact.py", text,
                           "b" * 40, "analysis")
    assert ("physics_harness.code.graph", "CROSS_OWNER_CANDIDATE") in {
        (v["module"], v["kind"]) for v in refs}
    assert ("physics_harness.code.analysis.local", "WITHIN_OWNER_CANDIDATE") in {
        (v["module"], v["kind"]) for v in refs}
    assert ("json", "OTHER_OR_UNRESOLVED_DEPENDENCY") in {
        (v["module"], v["kind"]) for v in refs}
    assert all(x["source_ref"].endswith("@" + "b" * 40) for x in refs)
