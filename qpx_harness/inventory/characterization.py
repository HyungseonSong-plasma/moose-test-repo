"""Canonical inventory-closure characterization preserving scientific contracts."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ..execution import cases as case_ops
from ..moose.input import MooseInput
from .closure_model import (
    _synthetic_closed_input,
    _synthetic_constrained_input,
    _target_only_pair_audit,
)
from .closure_runtime import (
    _evaluate_runtime_case_data,
    _evaluate_runtime_pair,
    _synthetic_runtime_row,
)
from .closure_schema import analyze_constraint_schema_text, analyze_drift_schema_text
from .constants import (
    C0_TARGET,
    C1_TARGET,
    CONSTRAINT_TYPE,
    DEFAULT_MACRO_ELECTRON_AVG,
    DRIFT_TYPE,
    LAMBDA_VARIABLE,
)
from .structure import (
    audit_closed_electron_structure,
    audit_constrained_quasisteady_structure,
)
from .orchestration import _stage_case, _write_json


def self_test() -> int:
    try:
        base = _synthetic_closed_input()
        if audit_closed_electron_structure(base)["status"] != "PASS":
            raise AssertionError("positive closed/source-free structure did not pass")
        missing_boundary = base.replace(" plasma_wafer", "", 1)
        if audit_closed_electron_structure(missing_boundary)["status"] == "PASS":
            raise AssertionError("missing drift boundary negative mutation was accepted")
        electron_bc, _ = MooseInput(base).insert_before_close(
            "FVBCs",
            """  [electron_leak]
    type = FVDirichletBC
    variable = n_e
    boundary = plasma_metal
    value = 1e16
  []""",
        )
        if audit_closed_electron_structure(electron_bc)["status"] == "PASS":
            raise AssertionError("n_e FVBC negative mutation was accepted")
        electron_source, _ = MooseInput(base).insert_before_close(
            "FVKernels",
            """  [electron_source]
    type = FVCoupledForce
    variable = n_e
    v = potential_plasma
  []""",
        )
        if audit_closed_electron_structure(electron_source)["status"] == "PASS":
            raise AssertionError("n_e source/sink negative mutation was accepted")

        good_drift_schema = {
            DRIFT_TYPE: {
                "description": "derived FVFluxKernel object",
                "parameters": {
                    "boundaries_to_avoid": {"description": "FVFluxKernel avoid"},
                    "boundaries_to_force": {"description": "FVFluxKernel force"},
                    "force_boundary_execution": {"description": "FVFluxKernel boundary execution"},
                },
            }
        }
        wrapped = "**START JSON DATA**\n" + json.dumps(good_drift_schema) + "\n**END JSON DATA**\n"
        if analyze_drift_schema_text(wrapped)["status"] != "PASS":
            raise AssertionError("valid FVFluxKernel schema evidence did not pass")
        if analyze_drift_schema_text(wrapped.replace("boundaries_to_force", "unrelated"))["status"] == "PASS":
            raise AssertionError("missing FVFluxKernel schema control was accepted")
        if analyze_drift_schema_text("{}\n")["status"] == "PASS":
            raise AssertionError("missing MOOSE JSON evidence was accepted")

        constrained = _synthetic_constrained_input()
        if audit_constrained_quasisteady_structure(
            constrained, expected_macro_avg=DEFAULT_MACRO_ELECTRON_AVG
        )["status"] != "PASS":
            raise AssertionError("positive constrained quasi-steady structure did not pass")
        with_time = constrained.replace(
            "[FVKernels]\n",
            "[FVKernels]\n  [time]\n    type = FVTimeKernel\n    variable = n_e\n  []\n",
            1,
        )
        if audit_constrained_quasisteady_structure(
            with_time, expected_macro_avg=DEFAULT_MACRO_ELECTRON_AVG
        )["status"] == "PASS":
            raise AssertionError("closure candidate retaining FVTimeKernel was accepted")
        wrong_target = constrained.replace(
            f"value = {DEFAULT_MACRO_ELECTRON_AVG:.17g}", "value = 2e16", 1
        )
        if audit_constrained_quasisteady_structure(
            wrong_target, expected_macro_avg=DEFAULT_MACRO_ELECTRON_AVG
        )["status"] == "PASS":
            raise AssertionError("wrong macro electron-average target was accepted")
        missing_lambda = constrained.replace(
            f"lambda = {LAMBDA_VARIABLE}", "lambda = missing_lambda", 1
        )
        if audit_constrained_quasisteady_structure(
            missing_lambda, expected_macro_avg=DEFAULT_MACRO_ELECTRON_AVG
        )["status"] == "PASS":
            raise AssertionError("constraint with wrong lambda coupling was accepted")

        good_constraint_schema = {
            CONSTRAINT_TYPE: {
                "description": "integral value constraint using a Lagrange multiplier",
                "parameters": {
                    "variable": {},
                    "lambda": {"description": "Lagrange multiplier variable"},
                    "phi0": {"description": "target average value"},
                },
            }
        }
        constraint_wrapped = (
            "**START JSON DATA**\n"
            + json.dumps(good_constraint_schema)
            + "\n**END JSON DATA**\n"
        )
        if analyze_constraint_schema_text(constraint_wrapped)["status"] != "PASS":
            raise AssertionError("valid inventory-constraint schema evidence did not pass")
        if analyze_constraint_schema_text(
            constraint_wrapped.replace('"phi0"', '"unrelated"', 1)
        )["status"] == "PASS":
            raise AssertionError("constraint schema missing phi0 was accepted")

        c0_text = _synthetic_constrained_input(C0_TARGET)
        c1_text = _synthetic_constrained_input(C1_TARGET)
        if _target_only_pair_audit(c0_text, c1_text)["status"] != "PASS":
            raise AssertionError("target-only C0/C1 pair did not pass")
        c1_mutated = c1_text.replace("boundary = outlet", "boundary = plasma_cover", 1)
        if _target_only_pair_audit(c0_text, c1_mutated)["status"] == "PASS":
            raise AssertionError("non-target C0/C1 construction mutation was accepted")

        good_diag = {
            "pc_failure_reason": None,
            "nonlinear_reason": None,
            "nonfinite_residuals": [],
            "variable_residuals": [
                {
                    "n_e": 1.0e-10,
                    "potential_plasma": 1.0e-12,
                    LAMBDA_VARIABLE: 1.0e-11,
                }
            ],
        }
        c0_eval = _evaluate_runtime_case_data(
            target=C0_TARGET,
            returncode=0,
            converged_marker=True,
            diagnostic=good_diag,
            row=_synthetic_runtime_row(C0_TARGET),
        )
        c1_eval = _evaluate_runtime_case_data(
            target=C1_TARGET,
            returncode=0,
            converged_marker=True,
            diagnostic=good_diag,
            row=_synthetic_runtime_row(C1_TARGET),
        )
        if _evaluate_runtime_pair(c0_eval, c1_eval, target0=C0_TARGET, target1=C1_TARGET)["class"] != "CONSTRAINED_QUASISTEADY_RUNTIME_PASS":
            raise AssertionError("positive C0/C1 runtime discriminator did not pass")
        bad_row = _synthetic_runtime_row(C1_TARGET)
        bad_row["n_avg"] = C1_TARGET * 1.001
        bad_row["inventory"] = bad_row["n_avg"] * bad_row["domain_volume"]
        if _evaluate_runtime_case_data(
            target=C1_TARGET,
            returncode=0,
            converged_marker=True,
            diagnostic=good_diag,
            row=bad_row,
        )["class"] != "CONSTRAINT_TARGET_TRACKING_FAIL":
            raise AssertionError("target-tracking negative control did not fail")
        zero_diag = {**good_diag, "pc_failure_reason": "FACTOR_NUMERIC_ZEROPIVOT"}
        if _evaluate_runtime_case_data(
            target=C0_TARGET,
            returncode=1,
            converged_marker=False,
            diagnostic=zero_diag,
            row=None,
        )["class"] != "SECONDARY_SINGULAR_MODE_SUSPECTED":
            raise AssertionError("secondary zero-pivot negative control was not classified")
        if _evaluate_runtime_case_data(
            target=C0_TARGET,
            returncode=0,
            converged_marker=True,
            diagnostic={**good_diag, "variable_residuals": []},
            row=_synthetic_runtime_row(C0_TARGET),
        )["class"] != "CLOSURE_EVIDENCE_INSUFFICIENT":
            raise AssertionError("missing residual evidence was over-classified")

        with tempfile.TemporaryDirectory() as tmp_name:
            root = Path(tmp_name)
            source = root / "source"
            source.mkdir()
            (source / "input.i").write_text("table_file = asset.dat\n")
            (source / "asset.dat").write_text("asset\n")
            (source / "input_out.csv").write_text("stale\n")
            (source / ".jitcache").mkdir()
            target = root / "target"
            refs = _stage_case(source, target, "table_file = asset.dat\n")
            expected_asset = str((target / "asset.dat").resolve())
            if refs != [expected_asset]:
                raise AssertionError("canonical case-reference path schema changed")
            if (target / "input_out.csv").exists() or (target / ".jitcache").exists():
                raise AssertionError("canonical case staging retained stale runtime artifacts")
            (target / "asset.dat").unlink()
            try:
                case_ops.validate_case_references(target)
            except case_ops.CaseError:
                pass
            else:
                raise AssertionError("missing staged asset negative control was accepted")

        with tempfile.TemporaryDirectory() as tmp_name:
            summary_path = Path(tmp_name) / "summary.json"
            _write_json(summary_path, {"probe": 1})
            if json.loads(summary_path.read_text()) != {"probe": 1}:
                raise AssertionError("canonical artifact writer changed summary payload")
    except Exception as exc:
        print(f"ISSUE45_INVENTORY_NULLSPACE_SELFTEST: FAIL ({exc})")
        print(f"ISSUE45_INVENTORY_CLOSURE_RUNTIME_SELFTEST: FAIL ({exc})")
        return 1
    print("ISSUE45_INVENTORY_NULLSPACE_SELFTEST: PASS")
    print("ISSUE45_INVENTORY_CLOSURE_RUNTIME_SELFTEST: PASS")
    return 0
