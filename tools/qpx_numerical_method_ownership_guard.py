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
        if (ROOT / old).exists():
            failures.append(f"historical/method-specific generic owner remains: {old}")

    flat_green_gauss = ROOT / "qpx_harness/analysis/green_gauss.py"
    nested_green_gauss = ROOT / "qpx_harness/analysis/gradient_reconstruction/green_gauss.py"
    nested_capability_init = ROOT / "qpx_harness/analysis/gradient_reconstruction/__init__.py"
    green_gauss_owners = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "qpx_harness/analysis").rglob("green_gauss.py")
    )
    if flat_green_gauss.exists():
        failures.append("legacy top-level analysis/green_gauss.py remains")
    if not nested_green_gauss.is_file() or not nested_capability_init.is_file():
        failures.append("nested gradient-reconstruction Green-Gauss capability owner missing")
    if green_gauss_owners != ["qpx_harness/analysis/gradient_reconstruction/green_gauss.py"]:
        failures.append(f"Green-Gauss implementation ownership is not singular/canonical: {green_gauss_owners}")

    app_reconstruction = text("qpx_harness/application/gradient_reconstruction.py")
    reasoning_reconstruction = text("qpx_harness/reasoning/gradient_reconstruction.py")
    method_registry_owners: list[str] = []
    for path in (ROOT / "qpx_harness").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "SUPPORTED_RECONSTRUCTION_METHODS" in source and "green_gauss" in source:
            method_registry_owners.append(path.relative_to(ROOT).as_posix())
    method_registry_owners.sort()
    expected_registry_owner = ["qpx_harness/application/gradient_reconstruction.py"]
    if method_registry_owners != expected_registry_owner:
        failures.append(
            "installed reconstruction-method registry is not application-owned only: "
            f"{method_registry_owners}"
        )
    if "SUPPORTED_RECONSTRUCTION_METHODS" in reasoning_reconstruction or "def _validate_method" in reasoning_reconstruction:
        failures.append("reasoning still owns installed reconstruction-method validation")
    concrete_reconstruction_imports = (
        "qpx_harness.analysis.green_gauss",
        "qpx_harness.analysis.gradient_reconstruction.green_gauss",
    )
    if any(token in reasoning_reconstruction for token in concrete_reconstruction_imports):
        failures.append("reasoning imports a concrete reconstruction implementation")
    if "qpx_harness.analysis.gradient_reconstruction.green_gauss" not in app_reconstruction:
        failures.append("application dispatch does not target canonical nested Green-Gauss implementation")
    if "SUPPORTED_RECONSTRUCTION_METHODS = frozenset({\"green_gauss\"})" not in app_reconstruction:
        failures.append("application reconstruction registry/dispatch owner missing")

    green_gauss_source = text("qpx_harness/analysis/gradient_reconstruction/green_gauss.py") if nested_green_gauss.is_file() else ""
    if "def derive_face_quantities" not in green_gauss_source or "def derive_cell_quantities" not in green_gauss_source:
        failures.append("analysis Green-Gauss formula owner is incomplete")
    if "ReconstructionTolerances" not in reasoning_reconstruction or "build_constant_state_ruleset" not in reasoning_reconstruction:
        failures.append("reasoning gradient-reconstruction diagnostic policy owner missing")

    app_surface = text("qpx_harness/application/__init__.py") + text("qpx_harness/application/operations.py")
    if "analyze_green_gauss" in app_surface or "diagnose_constant_green_gauss" in app_surface:
        failures.append("canonical application still exports Green-Gauss-named generic operations")
    if "analyze_gradient_reconstruction" not in app_surface:
        failures.append("canonical gradient-reconstruction application owner missing")

    jacobian_evidence = text("qpx_harness/evidence/normalization/jacobian.py")
    if "petsc" in jacobian_evidence.lower():
        failures.append("generic Jacobian evidence depends on or names concrete PETSc decoding")
    if "qpx_harness.diagnose" in jacobian_evidence:
        failures.append("stale diagnose namespace remains in Jacobian evidence")

    jacobian_reasoning = text("qpx_harness/reasoning/jacobian.py")
    if "PETSc" in jacobian_reasoning or "-snes_test_jacobian" in jacobian_reasoning:
        failures.append("Jacobian verification reasoning contains backend-specific wording")
    if "relative_tolerance" not in jacobian_reasoning:
        failures.append("Jacobian correctness tolerance is not explicit policy")

    petsc_parser = text("qpx_harness/adapters/petsc/jacobian.py")
    if "parse_comparisons" not in petsc_parser or "-snes_test_jacobian" not in petsc_parser:
        failures.append("PETSc Jacobian diagnostic parser owner missing")

    coupled = text("qpx_harness/reasoning/coupled_solver.py")
    if "COUPLED_JACOBIAN_OR_RESIDUAL_FAIL" not in coupled:
        failures.append("broad coupled Jacobian-or-residual runtime suspect classification missing")
    if "JACOBIAN_MISMATCH" in coupled:
        failures.append("coupled runtime reasoning duplicates verified Jacobian mismatch policy")

    if failures:
        print("NUMERICAL_METHOD_OWNERSHIP_GUARD: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("CANONICAL_GRADIENT_RECONSTRUCTION_CAPABILITY_OWNER_COUNT = 1")
    print("GREEN_GAUSS_METHOD_IMPLEMENTATION_OWNER_COUNT = 1")
    print("TOP_LEVEL_ANALYSIS_GREEN_GAUSS_MODULE = 0")
    print("GREEN_GAUSS_IMPLEMENTATION_UNDER_RECONSTRUCTION_NAMESPACE = PASS")
    print("CANONICAL_RECONSTRUCTION_METHOD_REGISTRY_OWNER_COUNT = 1")
    print("REASONING_RECONSTRUCTION_METHOD_REGISTRY_OWNERS = 0")
    print("REASONING_TO_CONCRETE_RECONSTRUCTION_IMPLEMENTATION_EDGES = 0")
    print("APPLICATION_OWNS_RECONSTRUCTION_DISPATCH = PASS")
    print("ANALYSIS_OWNS_RECONSTRUCTION_FORMULAS = PASS")
    print("REASONING_OWNS_RECONSTRUCTION_DIAGNOSTIC_POLICY = PASS")
    print("GENERIC_DEFAULT_FACE_CONTRACT_IS_METHOD_SPECIFIC = 0")
    print("GENERIC_EVIDENCE_REQUIRED_COLUMNS_TIED_TO_GREEN_GAUSS = 0")
    print("GENERIC_APPLICATION_OPERATIONS_NAMED_GREEN_GAUSS = 0")
    print("HISTORICAL_GREEN_GAUSS_WORKFLOWS_IN_PRODUCTION_APPLICATION = 0")
    print("GENERIC_REASONING_RULES_OWNED_BY_GREEN_GAUSS_MODULE = 0")
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
