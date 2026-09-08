from __future__ import annotations

from pathlib import Path

from qpx_harness.provenance.cases import QVT_PREPOISSON_CASE

ROOT = Path(__file__).resolve().parents[2]


def test_experiment_and_pytest_namespaces_are_distinct() -> None:
    experiments = ROOT / "experiments"
    tests = ROOT / "tests"
    assert experiments.is_dir()
    assert tests.is_dir()
    assert any(experiments.rglob("test.json"))
    assert not list(tests.rglob("test.json"))


def test_qvt_prepoisson_identity_uses_experiments_namespace() -> None:
    expected = Path("experiments/Issue2_electron_bulk_drift/qvt_prepoisson")
    assert QVT_PREPOISSON_CASE == expected
    assert (ROOT / expected / "test.json").is_file()


def test_default_pytest_python_sources_are_qpx_free() -> None:
    forbidden = ("qpx" + "-opt", "--" + "check-input")
    for path in (ROOT / "tests").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, (path, token)


def test_retired_execution_contract_facade_stays_absent() -> None:
    assert not (ROOT / "qpx_harness/execution_contract.py").exists()
    assert (ROOT / "qpx_harness/execution/contract.py").is_file()
