#!/usr/bin/env python3
"""Governed bounded pre-Maxwell Stage-5 acceptance runner for issue #176.

This surface composes the closed #192 S5-R assembly but corrects the dedicated
EI10/EI16 O2 source projectors to the canonical Stage-5 O2/O2+ molar-mass
ledger (0.032 kg/mol).  The correction is required because charge-density and
heavy-species number mappings use 0.032 kg/mol; retaining 0.031998 kg/mol in
those two projectors creates a deterministic particle/charge mismatch.

A green run establishes only bounded pre-Maxwell Stage-5 chemistry integration.
It does not establish long-time unpowered electron-energy stability, powered
RF/Maxwell closure, Stage-6 acceptance, or Integrated Physics Accuracy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from experiments.Issue192_s5r_representative import run as s5r
from physics_harness.adapters.moose import parameters as mp
from physics_harness.execution.cases import stage_case, validate_case_references

ROOT = Path(__file__).resolve().parents[2]
SOURCE = s5r.SOURCE
CANONICAL_O2_MOLAR_MASS = 0.032
END_TIME_S = 1.0e-5
CASE_SPECS = (("dt_10us", 1.0e-5), ("dt_5us", 5.0e-6))
INITIAL_INVENTORY_PPS = (
    "n_e_inventory",
    "domain_volume",
    "mass_total",
    "mass_O2",
    "mass_O2s",
    "mass_O2p",
    "mass_O",
    "mass_Om",
    "mass_Op",
    "mass_Os",
)


class Stage5AcceptanceError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_input(dt_s: float) -> tuple[str, dict[str, Any]]:
    """Return the #176 acceptance input with one canonical mass convention."""
    s5r.END_TIME_S = END_TIME_S
    text, meta = s5r._runtime_input(dt_s)

    for projector in ("s5r_ei10_projection", "s5r_ei16_projection"):
        text = mp.upsert_parameter(
            text,
            f"FunctorMaterials/{projector}",
            "o2_molar_mass",
            f"{CANONICAL_O2_MOLAR_MASS:.17g}",
        )

    # Inherited inventory postprocessors are TIMESTEP_END-only.  Their CSV
    # INITIAL row is otherwise zero even though the solver IC is nonzero.
    for pp in INITIAL_INVENTORY_PPS:
        text = mp.upsert_parameter(
            text,
            f"Postprocessors/{pp}",
            "execute_on",
            "'INITIAL TIMESTEP_END'",
        )

    audit = s5r.audit_s5r_input(text)
    if audit["status"] != "PASS":
        raise Stage5AcceptanceError(
            f"S5-R semantic audit failed after #176 correction: {audit['failed_checks']}"
        )

    for projector in ("s5r_ei10_projection", "s5r_ei16_projection"):
        value = float(
            mp.get_parameter(
                text,
                f"FunctorMaterials/{projector}",
                "o2_molar_mass",
            )
        )
        if value != CANONICAL_O2_MOLAR_MASS:
            raise Stage5AcceptanceError(
                f"{projector} molar mass {value} != canonical {CANONICAL_O2_MOLAR_MASS}"
            )

    meta = dict(meta)
    meta["issue176_acceptance_correction"] = {
        "canonical_O2_molar_mass_kg_per_mol": CANONICAL_O2_MOLAR_MASS,
        "corrected_projectors": ["s5r_ei10_projection", "s5r_ei16_projection"],
        "reason": (
            "align reaction mass projection with Stage-5 heavy/charge number mapping; "
            "0.031998 vs 0.032 produced deterministic C2 charge mismatch"
        ),
        "physical_horizon_s": END_TIME_S,
    }
    return text, meta


def _run_case(exe: Path, out: Path, name: str, dt_s: float, timeout: float) -> dict[str, Any]:
    case_dir = out / "cases" / name
    case_dir.parent.mkdir(parents=True, exist_ok=True)
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)

    text, meta = _canonical_input(dt_s)
    staged = stage_case(
        SOURCE,
        case_dir,
        input_text=text,
        purge_directory_names=(".jitcache", "checkpoint", "checkpoints"),
        purge_patterns=("input_out*", "*.log", "*.e", "*.exo", "prepare_evidence.json"),
    )
    s5r._copy_runtime_assets(case_dir)
    references = validate_case_references(case_dir)
    (case_dir / "prepare_evidence.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n"
    )

    p2 = s5r._p2(exe, case_dir, logs / f"{name}_p2.log", timeout=timeout)
    runtime: dict[str, Any] = {"returncode": None}
    evidence: dict[str, Any] = {"hard_pass": False}
    if p2["returncode"] == 0:
        runtime = s5r._runtime(
            exe,
            case_dir,
            logs / f"{name}_runtime.log",
            timeout=timeout,
        )
        if runtime["returncode"] == 0:
            evidence = s5r._analyze_case(case_dir, input_text=text)

    passed = (
        p2["returncode"] == 0
        and runtime.get("returncode") == 0
        and evidence.get("hard_pass") is True
    )
    return {
        "dt_s": dt_s,
        "end_time_s": END_TIME_S,
        "staging": staged,
        "references": references,
        "construction": meta,
        "p2": p2,
        "runtime": runtime,
        "evidence": evidence,
        "pass": passed,
    }


def _self_test() -> int:
    for _, dt_s in CASE_SPECS:
        text, _ = _canonical_input(dt_s)
        assert s5r.audit_s5r_input(text)["status"] == "PASS"
        for projector in ("s5r_ei10_projection", "s5r_ei16_projection"):
            assert float(
                mp.get_parameter(
                    text,
                    f"FunctorMaterials/{projector}",
                    "o2_molar_mass",
                )
            ) == CANONICAL_O2_MOLAR_MASS
    print("ISSUE176_STAGE5_ACCEPTANCE_SELFTEST_PASS")
    return 0


def run(args: argparse.Namespace) -> int:
    exe = args.physics_opt.resolve()
    if not exe.is_file() or not os.access(exe, os.X_OK):
        raise Stage5AcceptanceError(f"invalid physics-opt: {exe}")

    out = args.results_root.resolve()
    out.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "schema_version": 1,
        "issue": 176,
        "stage": "STAGE_5_BOUNDED_PRE_MAXWELL",
        "repository_head": os.environ.get("GITHUB_SHA"),
        "runtime_authority": "governed_ci_provenance_controlled",
        "physics_opt_sha256": _sha256(exe),
        "physical_horizon_s": END_TIME_S,
        "claim_boundary": {
            "on_green": "bounded pre-Maxwell representative Stage-5 chemistry integration accepted",
            "does_not_establish": [
                "long-time unpowered electron-energy stability",
                "RF/Maxwell powered ICP closure",
                "Stage-6 acceptance",
                "Integrated Physics Accuracy",
            ],
        },
        "canonical_mass_correction": {
            "O2_and_O2p_kg_per_mol": CANONICAL_O2_MOLAR_MASS,
            "projectors": ["EI10", "EI16"],
        },
        "cases": {},
        "timestep_sensitivity": {},
        "status": "NOT_RUN",
    }

    endpoints: dict[str, Any] = {}
    all_pass = True
    for name, dt_s in CASE_SPECS:
        result = _run_case(exe, out, name, dt_s, args.timeout)
        summary["cases"][name] = result
        all_pass = all_pass and result["pass"]
        if result["pass"]:
            endpoints[name] = result["evidence"]["endpoint"]

    if all_pass:
        summary["timestep_sensitivity"] = s5r._timestep_sensitivity(
            endpoints["dt_10us"], endpoints["dt_5us"]
        )
        summary["status"] = "STAGE5_BOUNDED_REPRESENTATIVE_ACCEPTED"
    else:
        summary["status"] = "STAGE5_BOUNDED_REPRESENTATIVE_FAIL"

    path = out / "summary.json"
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(path.read_text())
    return 0 if all_pass else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--physics-opt", type=Path)
    parser.add_argument("--results-root", type=Path, default=Path("stage5-176-bounded-results"))
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    if args.physics_opt is None:
        parser.error("--physics-opt is required unless --self-test is used")
    if args.timeout <= 0.0:
        parser.error("--timeout must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
