#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLASSIFICATION = ROOT / "docs/development/2026-09-02_issue89_post_science_classification.json"
INTERPRETATION = ROOT / "studies/issue45/evr3_interpretation.json"
STUDY = ROOT / "studies/issue45"
EXPECTED_STUDY_FILES = (
    "evidence_inventory.json",
    "hypothesis_audit.json",
    "evr3_protocol.json",
    "evr3_discriminator.py",
    "evr3_interpretation.json",
)
PRODUCTION_ROOTS = (ROOT / "qpx_harness", ROOT / "recipes", ROOT / "bin")


def fail(message: str) -> None:
    raise AssertionError(message)


def imports_from_studies(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except (OSError, SyntaxError) as exc:
        fail(f"cannot parse production Python {path}: {exc}")
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "studies" or alias.name.startswith("studies."):
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "studies" or module.startswith("studies."):
                hits.append(module)
    return hits


def main() -> int:
    classification = json.loads(CLASSIFICATION.read_text())
    interpretation = json.loads(INTERPRETATION.read_text())

    if classification.get("issue") != 89:
        fail("classification register is not bound to Issue89")
    if classification.get("parent_science_issue") != 45:
        fail("classification register is not bound to Issue45")
    if classification.get("science_state") != "FROZEN_OUTCOME_B":
        fail("Issue45 science is not frozen at Outcome B")
    if classification.get("scientific_evr_consumed_by_issue89") != 0:
        fail("Issue89 must not consume scientific EVR")
    if classification.get("framework_absorption") != "NONE_JUSTIFIED_AT_CURRENT_REUSE_LEVEL":
        fail("Issue89 unexpectedly claims framework absorption")

    science = interpretation.get("scientific_outcome", {})
    if science.get("class") != "B":
        fail("final scientific outcome is not B")
    if science.get("name") != "PHYSICAL_CLOSURE_VALID / NUMERICAL_BLOCKER_IDENTIFIED":
        fail("unexpected final scientific outcome name")
    if interpretation.get("evr", {}).get("after") != "3/3 consumed":
        fail("Issue45 final EVR ledger is not 3/3 consumed")
    if interpretation.get("governance", {}).get("additional_issue45_scientific_runtime_authorized") is not False:
        fail("additional Issue45 scientific runtime must remain unauthorized")

    observations = interpretation.get("observations", {})
    if observations.get("residual_fidelity_loss_observed") is not False:
        fail("final EVR3 residual-fidelity conclusion drifted")
    if float(observations.get("max_residual_separation_ratio", 0.0)) != 4.78030132112778:
        fail("final EVR3 residual-separation metric drifted")
    if float(observations.get("max_preconditioned_operator_conditioning_proxy", 0.0)) != 4.200641331042e16:
        fail("final EVR3 conditioning proxy drifted")

    artifacts = {item["path"]: item for item in classification.get("artifacts", [])}
    expected_paths = {f"studies/issue45/{name}" for name in EXPECTED_STUDY_FILES}
    if set(artifacts) != expected_paths:
        fail(f"Issue89 artifact register mismatch: {sorted(artifacts)}")
    for name in EXPECTED_STUDY_FILES:
        if not (STUDY / name).is_file():
            fail(f"missing frozen Issue45 study artifact: {name}")

    architecture = classification.get("architecture_decision", {})
    if architecture.get("new_qpx_harness_modules") != 0:
        fail("Issue89 added an unjustified qpx_harness module")
    if architecture.get("new_generic_to_issue_dependencies") != 0:
        fail("Issue89 introduced a generic -> Issue dependency")
    if architecture.get("scientific_runtime_required") is not False:
        fail("Issue89 must not require scientific runtime")
    if architecture.get("scientific_state_changed") is not False:
        fail("Issue89 must not change frozen science")

    study_import_hits: list[str] = []
    for root in PRODUCTION_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            hits = imports_from_studies(path)
            if hits:
                study_import_hits.append(f"{path.relative_to(ROOT)}: {hits}")
    if study_import_hits:
        fail("production imports study workspace: " + "; ".join(study_import_hits))

    # A generic-looking singular-value parser remains study-local because there is
    # no demonstrated second consumer yet. Do not silently create a canonical owner.
    for path in sorted((ROOT / "qpx_harness").rglob("*.py")):
        text = path.read_text()
        if "ksp_monitor_singular_value" in text or "sigma_max_over_min" in text:
            fail(f"unapproved singular-value study mechanic promoted into {path.relative_to(ROOT)}")

    script = (STUDY / "evr3_discriminator.py").read_text()
    required_delegations = (
        "from qpx_harness.execution.runtime import",
        "from qpx_harness.adapters.moose import log as moose_log",
        "from qpx_harness.adapters.moose import parameters as mp",
        "from qpx_harness.adapters.moose import petsc_options as po",
        "from qpx_harness.petsc import ksp",
        "from qpx_harness.petsc import log as petsc_log",
    )
    missing = [item for item in required_delegations if item not in script]
    if missing:
        fail(f"historical EVR3 reproduction script lost canonical delegations: {missing}")

    print("ISSUE89_POST_SCIENCE_CANONICALIZATION_GUARD: PASS")
    print("Issue89 framework absorption: NONE_JUSTIFIED_AT_CURRENT_REUSE_LEVEL")
    print("Issue89 scientific EVR: 0")
    print("Issue45 scientific state: FROZEN_OUTCOME_B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
