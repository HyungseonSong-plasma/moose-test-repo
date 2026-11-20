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
