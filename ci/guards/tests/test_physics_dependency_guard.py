"""Issue #743: prove the consolidated dependency Guard retains every selector gate.

The synthetic Python files are isolated from production source. These tests
exercise the real AST scanning and CLI selection paths, not mocked verdicts.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ci.guards import physics_dependency_guard as guard


SELECTORS = ("evidence", "analysis", "execution", "presentation", "repository", "cycle")


@pytest.mark.parametrize(
    ("name", "sources", "expected_failures"),
    (
        ("valid", {"evidence/valid.py": "import math\n"}, set()),
        (
            "evidence_to_analysis",
            {"evidence/invalid.py": "import physics_harness.analysis\n"},
            {"evidence"},
        ),
        (
            "analysis_to_cli",
            {"analysis/invalid.py": "from physics_harness.cli import app\n"},
            {"analysis", "presentation"},
        ),
        (
            "execution_to_retired_domain",
            {"execution/invalid.py": "import physics_harness.dmix\n"},
            {"execution"},
        ),
        (
            "non_cli_to_cli",
            {"evaluation/invalid.py": "import physics_harness.cli\n"},
            {"presentation"},
        ),
        (
            "repository_ci_reverse_import",
            {"evidence/invalid.py": "from ci import guards\n"},
            {"repository"},
        ),
        (
            "canonical_dependency_cycle",
            {
                "evidence/a.py": "import physics_harness.execution\n",
                "execution/b.py": "import physics_harness.evidence\n",
            },
            {"cycle"},
        ),
    ),
)
def test_all_is_exact_union_of_old_selectors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
    sources: dict[str, str],
    expected_failures: set[str],
) -> None:
    package = tmp_path / "physics_harness"
    for relative, source in sources.items():
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "PKG", package)

    results: dict[str, int] = {}
    for selector in (*SELECTORS, "all"):
        results[selector] = guard.main(["--check", selector])
        capsys.readouterr()

    actual_failures = {selector for selector in SELECTORS if results[selector] != 0}
    assert actual_failures == expected_failures, (name, results)
    assert (results["all"] != 0) == bool(actual_failures), (name, results)
