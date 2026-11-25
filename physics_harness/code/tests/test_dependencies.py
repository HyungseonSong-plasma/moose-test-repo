"""Generic dependency verifier P0: configurable constraints and source evidence."""
from __future__ import annotations

import hashlib

from physics_harness.code.diagnostics.collector import SourceInput, SourceRecord
from physics_harness.code.verification import (
    DependencyContract, verify_dependencies,
)


def contract():
    return DependencyContract.from_mapping({
        "schema_version": 1,
        "package_root": "sample_pkg",
        "canonical_packages": ["analysis", "cli", "service"],
        "legacy_packages": [],
        "repository_tool": "build_tools",
        "forbidden_edges": [
            {"source": "analysis", "target": "cli",
             "category": "analysis", "reason": "Presentation isolation"},
            {"source": "*", "target": "cli",
             "except_source": "cli", "category": "presentation",
             "reason": "No reverse presentation imports"},
        ],
    })


def source(path: str, text: str) -> SourceInput:
    raw = text.encode("utf-8")
    sha = hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()
    return SourceInput(
        SourceRecord(path, sha, "100644", len(raw)), raw,
    )


def test_configured_import_violation_keeps_precise_witness():
    item = source("sample_pkg/analysis/run.py", "import sample_pkg.cli\n")
    result = verify_dependencies((item,), contract())
    assert result.status == "FAIL"
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert (finding.category, finding.path, finding.line, finding.blob_sha) == (
        "analysis", item.record.path, 1, item.record.blob_sha,
    )
    assert not result.mutation_approved


def test_policy_is_external_and_generic():
    item = source("sample_pkg/service/serve.py", "import sample_pkg.cli\n")
    report = verify_dependencies((item,), contract())
    assert [item.category for item in report.findings] == ["presentation"]


def test_cycle_is_independent_of_forbidden_edge_rules():
    a = source("sample_pkg/analysis/a.py", "import sample_pkg.service\n")
    b = source("sample_pkg/service/b.py", "import sample_pkg.analysis\n")
    result = verify_dependencies((a, b), contract())
    assert result.status == "FAIL"
    assert {f.category for f in result.findings} == {"cycle"}


def test_bad_syntax_is_unverified():
    item = source("sample_pkg/analysis/bad.py", "def incomplete(\n")
    result = verify_dependencies((item,), contract())
    assert result.status == "UNVERIFIED"
    assert "INCOMPLETE_SOURCE_COVERAGE" in result.unverified_properties


def test_invalid_utf8_is_unverified():
    raw = b"\xff"
    item = SourceInput(
        SourceRecord("sample_pkg/analysis/bad.py", "a" * 40, "100644", 1), raw,
    )
    result = verify_dependencies((item,), contract())
    assert result.status == "UNVERIFIED"


def test_empty_scope_cannot_be_pass():
    result = verify_dependencies((), contract())
    assert result.status == "UNVERIFIED"


def test_duplicate_import_witness_uses_earliest_source_line_not_ast_visit():
    cases = (
        ("import sample_pkg.cli", "analysis", "sample_pkg.cli"),
        ("from sample_pkg.cli import entry", "analysis", "sample_pkg.cli"),
        ("tool = 'build_tools/scripts'", "repository", "build_tools/scripts"),
    )
    for statement, category, target in cases:
        # ast.walk visits the top-level occurrence before the nested one,
        # even though the nested occurrence appears earlier in source text.
        text = f"def earlier():\n    {statement}\n\n{statement}\n"
        item = source("sample_pkg/analysis/duplicates.py", text)
        result = verify_dependencies((item,), contract())
        assert result.status == "FAIL"
        assert len(result.findings) == 1  # first-match rule policy still wins
        finding = result.findings[0]
        assert (finding.category, finding.target, finding.line) == (
            category, target, 2,
        )
        assert (finding.path, finding.blob_sha) == (
            item.record.path, item.record.blob_sha,
        )


def test_cycle_witness_uses_earliest_line_of_duplicate_canonical_edge():
    a = source(
        "sample_pkg/analysis/dependency.py",
        "def earlier():\n    import sample_pkg.service\n\nimport sample_pkg.service\n",
    )
    b = source("sample_pkg/service/dependency.py", "import sample_pkg.analysis\n")
    report = verify_dependencies((b, a), contract())
    assert report.status == "FAIL"
    assert [finding.category for finding in report.findings] == ["cycle"]
    cycle = report.findings[0]
    assert (cycle.path, cycle.line, cycle.blob_sha) == (
        a.record.path, 2, a.record.blob_sha,
    )
    assert cycle.target == "analysis -> service -> analysis"


def _independence_contract():
    return DependencyContract.from_mapping({
        "schema_version": 1, "package_root": "libs",
        "canonical_packages": ["alpha", "beta"], "legacy_packages": [],
        "repository_tool": "build_tools", "forbidden_edges": [],
        "independent_packages": ["alpha", "beta"],
    })


def _design_report(git_factory, files, *, required=None, roots=None):
    from physics_harness.code.diagnostics import GitSourceProvider, ScanRequest, run_scan
    from physics_harness.code.verification import analyze_independent_dependencies
    files = {"libs/__init__.py": "", "libs/beta/__init__.py": "", **files}
    paths = tuple(sorted(files))
    root, sha = git_factory(files)
    result = run_scan(ScanRequest(repository="example/repo", revision=sha,
                                 includes=paths, collectors=("python_ast",)),
                      GitSourceProvider(root))
    return analyze_independent_dependencies(result.graph, result.receipt,
        _independence_contract(), required_paths=required or paths,
        stdlib_modules=frozenset({"os", "sys", "importlib", "__future__", "subprocess", "pathlib"}),
        repository_roots=roots if roots is not None else frozenset({"physics_harness"}))


def test_design_stdlib_and_local_imports(git_factory):
    result = _design_report(git_factory, {"libs/alpha/a.py": "import os\nfrom . import b\n",
                                         "libs/alpha/b.py": "import sys\n"})
    assert result.status == "NO_STATIC_VIOLATION_OBSERVED"
    assert {o.category for o in result.observations} == {"STDLIB_CANDIDATE", "SAME_PACKAGE"}
    assert not result.findings and not result.runtime_independence_proven
    assert not result.mutation_approved


def test_design_cross_package_cycle_and_upper_layer(git_factory):
    result = _design_report(git_factory, {
        "libs/alpha/a.py": "from ..beta import b\nimport physics_harness\n",
        "libs/beta/b.py": "import libs.alpha.a\n"})
    assert result.status == "DESIGN_VIOLATION_OBSERVED"
    assert result.cycle == ("alpha", "beta", "alpha")
    assert {f.category for f in result.findings} == {"CROSS_PACKAGE", "REPOSITORY_DEPENDENCY"}
    assert all(o.evidence_id and o.blob_sha and o.line > 0 for o in result.observations)


def test_design_nonstdlib_and_dynamic(git_factory):
    result = _design_report(git_factory, {"libs/alpha/a.py":
        "import requests\nimport importlib\nimportlib.import_module(name)\n"})
    assert result.status == "DESIGN_VIOLATION_OBSERVED"
    assert {"NON_STDLIB_OR_UNRESOLVED", "DYNAMIC_UNRESOLVED"} <= {o.category for o in result.observations}
    assert result.unknowns


def test_design_missing_path_and_overdepth_relative(git_factory):
    result = _design_report(git_factory, {"libs/alpha/a.py": "from ... import x\n"},
        required=("libs/__init__.py", "libs/alpha/a.py", "libs/alpha/missing.py", "libs/beta/__init__.py"))
    assert result.status == "REVIEW_REQUIRED"
    assert "SOURCE_NOT_FULLY_SCANNED:libs/alpha/missing.py" in result.unknowns
    assert any(o.category == "UNRESOLVED_RELATIVE" for o in result.observations)


def test_design_repo_shadow_and_parent_init(git_factory):
    result = _design_report(git_factory, {"libs/alpha/a.py": "import os\n",
        "libs/__init__.py": "from . import beta\n"}, roots=frozenset({"os"}))
    assert result.status == "DESIGN_VIOLATION_OBSERVED"
    assert {f.category for f in result.findings} == {"CROSS_PACKAGE", "REPOSITORY_DEPENDENCY"}


def test_design_contract_not_accepted_by_legacy_verifier():
    import pytest
    with pytest.raises(ValueError, match="DESIGN_ONLY_DEPENDENCY_CONTRACT"):
        verify_dependencies((), _independence_contract())



def test_design_reports_execution_and_resource_candidates_not_proven_violations(git_factory):
    result = _design_report(git_factory, {"libs/alpha/a.py":
        "import subprocess\nimport os\nfrom pathlib import Path\n"
        "subprocess.run(['git', 'status'])\n"
        "Path('config.json')\n"
        "os.getenv('HOME')\n"
        "value = os.environ\n"})
    categories = {o.category for o in result.observations}
    assert {"EXECUTION_CANDIDATE", "RESOURCE_REFERENCE_CANDIDATE",
            "RESOURCE_ACCESS_CANDIDATE"} <= categories
    assert result.status == "REVIEW_REQUIRED"
    assert not result.findings and not result.runtime_independence_proven
    assert all(o.evidence_id and o.blob_sha for o in result.observations)


def test_design_does_not_mistake_arbitrary_function_call_for_tool_execution(git_factory):
    result = _design_report(git_factory, {"libs/alpha/a.py":
        "def run():\n    return 1\nrun()\n"})
    assert not result.findings
    assert not any(o.category == "EXECUTION_CANDIDATE" for o in result.observations)
    assert result.status == "NO_STATIC_VIOLATION_OBSERVED"
