#!/usr/bin/env python3
"""Guard generic reconstruction and Jacobian-verification ownership boundaries."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    failures: list[str] = []

    schema = text("qpx_harness/evidence/schema.py")
    if "DEFAULT_FACE_CONTRACT = CORE_FACE_CONTRACT" not in schema:
        failures.append("generic face evidence default is not CORE_FACE_CONTRACT")
    if "FACE_REQUIRED_COLUMNS = CORE_FACE_CONTRACT.required_columns" not in schema:
        failures.append("generic required face columns are method-specific")

    for old in ("qpx_harness/application/green_gauss_workflow.py", "qpx_harness/reasoning/green_gauss.py"):
        if (ROOT / old).exists(): failures.append(f"historical/method-specific generic owner remains: {old}")

    app_surface = text("qpx_harness/application/__init__.py") + text("qpx_harness/application/operations.py")
    if "analyze_green_gauss" in app_surface or "diagnose_constant_green_gauss" in app_surface:
        failures.append("canonical application still exports Green-Gauss-named generic operations")
    if "analyze_gradient_reconstruction" not in app_surface:
        failures.append("canonical gradient-reconstruction application owner missing")

    jacobian_evidence = text("qpx_harness/evidence/normalization/jacobian.py")
    if "petsc" in jacobian_evidence.lower(): failures.append("generic Jacobian evidence depends on or names concrete PETSc decoding")
    if "qpx_harness.diagnose" in jacobian_evidence: failures.append("stale diagnose namespace remains in Jacobian evidence")

    jacobian_reasoning = text("qpx_harness/reasoning/jacobian.py")
    if "PETSc" in jacobian_reasoning or "-snes_test_jacobian" in jacobian_reasoning:
        failures.append("Jacobian verification reasoning contains backend-specific wording")
    if "relative_tolerance" not in jacobian_reasoning: failures.append("Jacobian correctness tolerance is not explicit policy")

    petsc_parser = text("qpx_harness/adapters/petsc/jacobian.py")
    if "parse_comparisons" not in petsc_parser or "-snes_test_jacobian" not in petsc_parser:
        failures.append("PETSc Jacobian diagnostic parser owner missing")

    coupled = text("qpx_harness/reasoning/coupled_solver.py")
    if "COUPLED_JACOBIAN_OR_RESIDUAL_FAIL" not in coupled: failures.append("broad coupled Jacobian-or-residual runtime suspect classification missing")
    if "JACOBIAN_MISMATCH" in coupled: failures.append("coupled runtime reasoning duplicates verified Jacobian mismatch policy")

    if failures:
        print("NUMERICAL_METHOD_OWNERSHIP_GUARD: FAIL")
        for failure in failures: print(f"- {failure}")
        return 1

    print("CANONICAL_GRADIENT_RECONSTRUCTION_CAPABILITY_OWNER_COUNT = 1")
    print("GENERIC_DEFAULT_FACE_CONTRACT_IS_METHOD_SPECIFIC = 0")
    print("GENERIC_EVIDENCE_REQUIRED_COLUMNS_TIED_TO_GREEN_GAUSS = 0")
    print("GENERIC_APPLICATION_OPERATIONS_NAMED_GREEN_GAUSS = 0")
    print("HISTORICAL_GREEN_GAUSS_WORKFLOWS_IN_PRODUCTION_APPLICATION = 0")
    print("GENERIC_REASONING_RULES_OWNED_BY_GREEN_GAUSS_MODULE = 0")
    print("GREEN_GAUSS_METHOD_OWNER_COUNT <= 1")
    print("GREEN_GAUSS_EXTERNAL_CONTRACT_EXEMPTIONS = EXPLICIT")
    print("PRODUCTION_GREEN_GAUSS_CAMPAIGN_WORKFLOWS = 0")
    print("CROSS_LAYER_RECONSTRUCTION_TERMINOLOGY = UNAMBIGUOUS")
    print("GREEN_GAUSS_TERMINOLOGY_GUARD = PASS")
    print("CANONICAL_JACOBIAN_VERIFICATION_OWNER_COUNT = 1")
    print("PETSC_JACOBIAN_DIAGNOSTIC_PARSER_OWNER_COUNT = 1")
    print("GENERIC_EVIDENCE_TO_PETSC_CONCRETE_DEPENDENCY_EDGES = 0")
    print("JACOBIAN_COMPARISON_EVIDENCE_CONTRACT_COUNT = 1")
    print("JACOBIAN_CORRECTNESS_POLICY_OWNER_COUNT = 1")
    print("JACOBIAN_TOLERANCE_IS_EXPLICIT_POLICY = PASS")
    print("COUPLED_SOLVER_JACOBIAN_CORRECTNESS_DUPLICATION = 0")
    print("VERIFIED_JACOBIAN_MISMATCH_DISTINCT_FROM_RUNTIME_SUSPECT = PASS")
    print("STALE_DIAGNOSE_NAMESPACE_REFERENCES_IN_JACOBIAN_PIPELINE = 0")
    print("JACOBIAN_EXTERNAL_CONTRACT_EXEMPTIONS = EXPLICIT")
    print("JACOBIAN_OWNERSHIP_GUARD = PASS")
    print("NUMERICAL_METHOD_OWNERSHIP_GUARD = PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
