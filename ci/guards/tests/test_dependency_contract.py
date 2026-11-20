"""#743: frozen negative controls for the accepted dependency contract."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from physics_harness.code.diagnostics.collector import SourceInput, SourceRecord
from physics_harness.code.verification import (
    DependencyContract, verify_dependencies,
)


ROOT = Path(__file__).resolve().parents[3]

CASES = (
    ("valid", {"evidence/valid.py": "import math\n"}, set()),
    ("evidence_to_analysis", {
        "evidence/invalid.py": "import physics_harness.analysis\n"}, {"evidence"}),
    ("evidence_to_diagnose", {
        "evidence/invalid.py": "import physics_harness.diagnose\n"}, {"evidence"}),
    ("analysis_to_cli", {
        "analysis/invalid.py": "from physics_harness.cli import app\n"}, {"analysis"}),
    ("analysis_to_validation", {
        "analysis/invalid.py": "import physics_harness.validation\n"}, {"analysis"}),
    ("execution_to_retired_domain", {
        "execution/invalid.py": "import physics_harness.dmix\n"}, {"execution"}),
    ("non_cli_to_cli", {
        "evaluation/invalid.py": "import physics_harness.cli\n"}, {"presentation"}),
    ("repository_reverse_import", {
        "evidence/invalid.py": "from ci import guards\n"}, {"repository"}),
    ("repository_path_literal", {
        "evidence/invalid.py": 'CONFIG = "ci/guards/settings.json"\n'}, {"repository"}),
    ("canonical_cycle", {
        "evidence/a.py": "import physics_harness.execution\n",
        "execution/b.py": "import physics_harness.evidence\n",
    }, {"cycle"}),
)


def make_sources(root: Path, files: dict[str, str]) -> tuple[SourceInput, ...]:
    result: list[SourceInput] = []
    for relative, contents in files.items():
        path = root / "physics_harness" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = contents.encode("utf-8")
        path.write_bytes(raw)
        blob = hashlib.sha1(
            b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
        ).hexdigest()
        record = SourceRecord(
            path="physics_harness/" + relative,
            blob_sha=blob, mode="100644", size=len(raw),
        )
        result.append(SourceInput(record, raw))
    return tuple(result)


@pytest.mark.parametrize(("name", "files", "expected"), CASES)
def test_harness_matches_accepted_legacy_negative_verdicts(
    tmp_path: Path, name: str, files: dict[str, str], expected: set[str],
) -> None:
    sources = make_sources(tmp_path, files)

    contract = DependencyContract.from_mapping(json.loads(
        (ROOT / "ci/contracts/harness_dependencies.json").read_text(
            encoding="utf-8"
        )
    ))
    result = verify_dependencies(sources, contract)
    new_failures = {finding.category for finding in result.findings}

    assert new_failures == expected, (name, new_failures)
    assert (result.status == "FAIL") == bool(expected)
    assert result.checked_files == len(sources)
    assert result.mutation_approved is False
    assert "SEMANTIC_AND_RUNTIME_COMPATIBILITY_UNPROVEN" in result.unverified_properties


def test_unsupported_source_does_not_receive_false_pass(tmp_path: Path) -> None:
    sources = make_sources(tmp_path, {"analysis/broken.py": "def broken(\n"})
    contract = DependencyContract.from_mapping(json.loads(
        (ROOT / "ci/contracts/harness_dependencies.json").read_text(
            encoding="utf-8"
        )
    ))
    report = verify_dependencies(sources, contract)
    assert report.status == "UNVERIFIED"
    assert "INCOMPLETE_SOURCE_COVERAGE" in report.unverified_properties
