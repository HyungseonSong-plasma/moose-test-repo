#!/usr/bin/env python3
"""Code3 PR-A: electron-only Custom vs FVCoupledForce input A/B.

Source-bound preparation and P0/P2 qualification. Native residual/Jacobian
equivalence is NOT asserted by this script. Historical W5 source owners,
transport, energy projection, heavy source kernels and acceptance values stay
unchanged. This tool never edits production generators or retires C++.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from physics_harness.adapters.moose import parameters as mp
from physics_harness.adapters.moose.input import MooseInput
from physics_harness.execution.cases import stage_case, validate_case_references

TARGET = "FVKernels/s5r_electron_source"
OLD = "PhysicsFVElectronReactionSource"
NEW = "FVCoupledForce"


class Code3ParityError(RuntimeError):
    pass


def _source_coefficient(text: str, path: str) -> tuple[str, float, str]:
    if mp.get_parameter(text, path, "type") != OLD:
        raise Code3ParityError("EXPECTED_CUSTOM_ELECTRON_SOURCE")
    source = mp.get_parameter(text, path, "number_source")
    if not source or not source.strip():
        raise Code3ParityError("MISSING_SIGNED_SOURCE_FUNCTOR")
    mode = mp.get_parameter(text, path, "state_form") or "normalized"
    if mode not in {"physical", "normalized"}:
        raise Code3ParityError("UNKNOWN_STATE_FORM:" + mode)
    if mode == "physical":
        return source, 1.0, mode
    raw = mp.get_parameter(text, path, "n_ref")
    if raw is None:
        raise Code3ParityError("NORMALIZED_N_REF_REQUIRED")
    try:
        n_ref = float(raw)
    except ValueError as exc:
        raise Code3ParityError("NORMALIZED_N_REF_NOT_LITERAL") from exc
    if not math.isfinite(n_ref) or n_ref <= 0:
        raise Code3ParityError("NORMALIZED_N_REF_MUST_BE_FINITE_POSITIVE")
    coef = 1.0 / n_ref
    if not math.isfinite(coef) or coef <= 0:
        raise Code3ParityError("NORMALIZED_COEF_NOT_FINITE_POSITIVE")
    return source, coef, mode


def _outside_target(text: str, path: str = TARGET) -> tuple[str, str]:
    span = MooseInput(text).unique(path)
    return text[:span.start], text[span.end:]


def replace_electron_only(text: str, path: str = TARGET) -> tuple[str, dict]:
    """Rewrite exactly one electron source block; all other bytes must match."""
    source, coef, mode = _source_coefficient(text, path)
    original_outside = _outside_target(text, path)
    result = mp.upsert_parameter(text, path, "type", NEW)
    result = mp.remove_parameter(result, path, "number_source")
    result = mp.remove_parameter(result, path, "state_form")
    result = mp.remove_parameter(result, path, "n_ref")
    result = mp.upsert_parameter(result, path, "v", source)
    result = mp.upsert_parameter(result, path, "coef", format(coef, ".17g"))
    if _outside_target(result, path) != original_outside:
        raise Code3ParityError("NON_ELECTRON_INPUT_CHANGED")
    if (mp.get_parameter(result, path, "type") != NEW
            or mp.get_parameter(result, path, "v") != source
            or not math.isclose(float(mp.get_parameter(result, path, "coef") or "nan"),
                                coef, rel_tol=0.0, abs_tol=0.0)):
        raise Code3ParityError("ELECTRON_REWIRE_INVARIANT_FAILED")
    for old_param in ("number_source", "state_form", "n_ref"):
        if mp.get_parameter(result, path, old_param) is not None:
            raise Code3ParityError("CUSTOM_PARAMETER_REMAINED:" + old_param)
    return result, {"path": path, "old_type": OLD, "new_type": NEW,
                    "source_functor": source, "mode": mode, "coefficient": coef,
                    "non_target_bytes_unchanged": True,
                    "residual_formula_expected": "-coef * source_functor",
                    "runtime_parity": "NOT_EVALUATED"}


def build_pair() -> tuple[str, str, dict]:
    """Use exactly one W5 assembly for both branches: one changed block."""
    # Import W5 only for real generation: the pure P0 contract must run
    # on Repository CI's minimal Python installation without polars/Native.
    from experiments.Issue216_w5_multistep_acceptance import run as w5
    generated, meta = w5._build_case(
        dt_s=w5.BASELINE_DT_S, uniform_refine=0)
    # The active W5 route is now standard. Reconstruct the historical *input*
    # as an offline A/B fixture; never try to execute the retired Factory.
    from experiments.Code3_electron_source_retirement.consumer_pairs import virtual_legacy_from_current
    custom = virtual_legacy_from_current(generated, TARGET, "S_e_s5r", "normalized")
    standard, change = replace_electron_only(custom)
    if mp.get_parameter(custom, TARGET, "number_source") != "S_e_s5r":
        raise Code3ParityError("W5_HISTORICAL_SIGNED_SOURCE_OWNER_CHANGED")
    if mp.get_parameter(generated, TARGET, "type") != NEW or mp.get_parameter(generated, TARGET, "v") != "S_e_s5r":
        raise Code3ParityError("W5_CURRENT_STANDARD_SOURCE_CHANGED")
    if not math.isclose(float(mp.get_parameter(generated, TARGET, "coef") or "nan"),
                        change["coefficient"], rel_tol=1e-15):
        raise Code3ParityError("W5_CURRENT_STANDARD_NORMALIZED_COEF_CHANGED")
    return custom, generated, {"baseline": meta, "change": change, "historical_old_arm": "VIRTUAL_INPUT_ONLY"}


def self_test() -> dict:
    """Pure input contract: no W5 imports, no solver, no science PASS."""
    raw = ("[FVKernels]\n"
           "  [s5r_electron_source]\n"
           "    type = PhysicsFVElectronReactionSource\n"
           "    variable = n_e\n"
           "    number_source = S_e_s5r\n"
           "    n_ref = 4\n"
           "    block = plasma\n"
           "  []\n"
           "  [heavy]\n"
           "    type = PhysicsFVSpeciesReactionSource\n"
           "  []\n"
           "[]\n")
    custom = raw
    standard, meta = replace_electron_only(custom)
    physical = custom.replace("    n_ref = 4\n",
                              "    state_form = physical\n")
    physical_std, physical_meta = replace_electron_only(physical)
    checks = {
        "electron_only": _outside_target(custom) == _outside_target(standard),
        "custom_type": mp.get_parameter(custom, TARGET, "type") == OLD,
        "standard_type": mp.get_parameter(standard, TARGET, "type") == NEW,
        "same_source_functor": mp.get_parameter(standard, TARGET, "v") == "S_e_s5r",
        "normalized_nonunit_coefficient": meta["coefficient"] == 0.25,
        "physical_unscaled": physical_meta["coefficient"] == 1.0
                             and mp.get_parameter(physical_std, TARGET, "coef") == "1",
        "no_custom_parameters": all(
            mp.get_parameter(standard, TARGET, name) is None
            for name in ("number_source", "state_form", "n_ref")),
        "heavy_source_preserved": "PhysicsFVSpeciesReactionSource" in standard,
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "full_w5_generator": "NOT_EXECUTED",
            "native_evidence": "NOT_EXECUTED",
            "numeric_equivalence": "NOT_PROVEN", "safe_delete": "HOLD"}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prepare(out: Path, executable: Path | None = None, timeout: float = 180.0) -> dict:
    from experiments.Issue192_s5r_representative import run as s5r
    if out.exists():
        raise Code3ParityError("OUTPUT_ROOT_ALREADY_EXISTS")
    custom, standard, meta = build_pair()
    out.mkdir(parents=True)
    cases = {}
    for name, input_text in (("custom", custom), ("standard", standard)):
        case_dir = out / name
        staged = stage_case(
            s5r.SOURCE, case_dir, input_text=input_text,
            purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
            purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"))
        s5r._copy_runtime_assets(case_dir)
        refs = validate_case_references(case_dir)
        record = {"input_sha256": _digest(input_text), "input_path": str(case_dir / "input.i"),
                  "staging": staged, "references": refs, "P2": "NOT_EXECUTED"}
        if executable:
            if not executable.is_file():
                raise Code3ParityError("PHYSICS_OPT_MISSING")
            record["P2"] = s5r._p2(
                executable, case_dir, out / (name + "_p2.log"), timeout=timeout)
        cases[name] = record
    report = {"schema": "code3.electron_source_ab.v0.1",
              "target": OLD, "candidate": NEW,
              "scope": "ELECTRON_SOURCE_ONLY", "change": meta["change"],
              "cases": cases, "P3": "NOT_EXECUTED",
              "residual_jacobian_parity": "NOT_EVALUATED",
              "numerical_equivalence": "NOT_PROVEN", "safe_delete": "HOLD"}
    (out / "evidence.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--prepare", type=Path)
    parser.add_argument("--physics-opt", type=Path, help="Optional P2 --check-input; not P3")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()
    if args.self_test:
        result = self_test()
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    if args.prepare is None:
        parser.error("--prepare is required unless --self-test")
    report = prepare(args.prepare, args.physics_opt, timeout=args.timeout)
    print(json.dumps({"evidence": str(args.prepare / "evidence.json"),
                      "P2": {k: v["P2"] for k, v in report["cases"].items()},
                      "safe_delete": "HOLD"}, indent=2))
    return 0 if all(
        c["P2"] == "NOT_EXECUTED" or c["P2"].get("returncode") == 0
        for c in report["cases"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
