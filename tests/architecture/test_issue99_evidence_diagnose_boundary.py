from __future__ import annotations

import ast
from pathlib import Path

import qpx_harness.evidence as evidence
import qpx_harness.reasoning as reasoning
from qpx_harness.petsc.jacobian import parse_comparisons
from qpx_harness.reasoning.jacobian import diagnose_jacobian_evidence


def _absolute_imports(root: Path) -> set[str]:
    names: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module)
    return names


def test_evidence_runtime_ingest_emits_facts_not_diagnosis() -> None:
    facts = evidence.runtime_core_facts("", returncode=0)
    assert facts["returncode"] == 0
    assert "class" not in facts
    assert "status" not in facts
    assert "primary_owner_class" not in facts


def test_jacobian_is_split_into_backend_decode_evidence_then_validation() -> None:
    text = "||J - Jfd||_F/||J||_F = 1.0e-4, ||J - Jfd||_F = 2.0e-4"
    decoded = parse_comparisons(text)
    facts = evidence.extract_jacobian_evidence(
        decoded, provenance="petsc:snes_test_jacobian"
    )
    assert facts["comparison_count"] == 1
    assert facts["provenance"] == "petsc:snes_test_jacobian"
    assert "class" not in facts
    assert "status" not in facts

    canonical_pass = diagnose_jacobian_evidence(facts, relative_tolerance=1.0e-3)
    canonical_fail = diagnose_jacobian_evidence(facts, relative_tolerance=1.0e-5)
    assert canonical_pass["class"] == "JACOBIAN_CORRECTNESS_PASS"
    assert canonical_fail["class"] == "JACOBIAN_MISMATCH"


def test_coupled_solver_priority_is_owned_by_reasoning() -> None:
    base = {
        "returncode": 1,
        "linear_reason": None,
        "nonlinear_reason": None,
        "pc_failure_reason": None,
        "pc_hits": [],
        "factorization_hits": [],
        "variable_residuals": [],
        "nonfinite_residuals": [],
        "automatic_scaling_factors": [],
        "scaling_invalid": [],
        "scaling_factor_ratio": None,
    }

    pc = {**base, "pc_hits": ["PC failed"], "nonfinite_residuals": [{"x": 1}]}
    nonfinite = {**base, "nonfinite_residuals": [{"x": 1}]}
    scaling = {**base, "scaling_invalid": [{"variable": "n_e"}]}
    finite_failure = {**base, "variable_residuals": [{"n_e": 1.0}]}
    insufficient = {**base, "returncode": 0}

    assert reasoning.diagnose_coupled_runtime_evidence(pc)["class"] == "PC_OR_FACTORIZATION_FAIL"
    assert reasoning.diagnose_coupled_runtime_evidence(nonfinite)["class"] == "INITIAL_NONFINITE_FAIL"
    assert reasoning.diagnose_coupled_runtime_evidence(scaling)["class"] == "SCALING_DOMINATED_FAIL"
    assert reasoning.diagnose_coupled_runtime_evidence(finite_failure)["class"] == "COUPLED_JACOBIAN_OR_RESIDUAL_FAIL"
    assert reasoning.diagnose_coupled_runtime_evidence(insufficient)["class"] == "DIAGNOSTIC_INSUFFICIENT"


def test_canonical_dependency_direction_is_enforced() -> None:
    package_root = Path(evidence.__file__).resolve().parent.parent
    evidence_imports = _absolute_imports(package_root / "evidence")
    reasoning_imports = _absolute_imports(package_root / "reasoning")

    assert not any(name.startswith("qpx_harness.reasoning") for name in evidence_imports)
    assert not any(name.startswith("qpx_harness.petsc") for name in evidence_imports)
    assert not any(name.startswith("qpx_harness.adapters.moose") for name in reasoning_imports)
    assert not any(name.startswith("qpx_harness.petsc") for name in reasoning_imports)
    assert not any(name.startswith("qpx_harness.diagnose") for name in reasoning_imports)
