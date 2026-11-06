#!/usr/bin/env python3
"""Issue282 research-only 2D RZ crash localization; NEVER science acceptance.

Same historical geometry, application, fixed plasma data and registration-name
projection; compare the original heavy base, E1 energy time term, E2a D=0,
and E2a D=100. Do not silence segfaults or relabel them physics failure.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.Issue26_electron_energy.E2a_controlled_diffusion.run import _stage_case
from experiments.historical_recipe_support.issue26_e1 import build_issue26_e1_input
from experiments.Issue282_e2a_rz_bridge.research_type_bridge import (
    project_historical_registration_only,
    HISTORICAL_TO_CURRENT_TYPE,
    TYPE_LINE,
)
from experiments.Issue282_e2a_rz_bridge.run_native import (
    run_native,
    PER_CASE_TIMEOUT,
)
from physics_harness.adapters.moose import parameters as mp

HERE = Path(__file__).resolve().parent
CASES = ("heavy_base", "e1_energy_time", "e2a_zero_diffusion", "e2a_diffusion")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()



def project_subset_registration_only(text: str) -> tuple[str, dict]:
    """Reversible whitelist projection for earlier predecessor states."""
    present = {m.group("name") for m in TYPE_LINE.finditer(text)
               if m.group("name").startswith("QPX")}
    known = set(HISTORICAL_TO_CURRENT_TYPE)
    if not present or not present <= known:
        raise ValueError(f"unknown or empty historical QPX type set: {sorted(present - known)}")
    if present == known:
        return project_historical_registration_only(text)
    reverse = {v: k for k,v in HISTORICAL_TO_CURRENT_TYPE.items()}
    projected = TYPE_LINE.sub(
        lambda m: m.group("prefix") +
        HISTORICAL_TO_CURRENT_TYPE.get(m.group("name"), m.group("name")) +
        m.group("suffix"), text)
    restored = TYPE_LINE.sub(
        lambda m: m.group("prefix") +
        reverse.get(m.group("name"), m.group("name")) + m.group("suffix"), projected)
    if restored != text:
        raise ValueError("predecessor projection was not exactly reversible")
    return projected, {"status": "WHITELIST_SUBSET_REGISTRATION_ONLY", "source_types": sorted(present)}


def make_case(case_dir: Path, name: str) -> dict:
    _stage_case(case_dir, diffusivity_m2_s=0.0 if name != "e2a_diffusion" else 100.0)
    base = (case_dir / "heavy_base.i").read_text(encoding="utf-8")
    if name == "heavy_base":
        original = base
    elif name == "e1_energy_time":
        original, meta = build_issue26_e1_input(base, initial_energy_hat=1.0)
        if meta["audit"]["status"] != "PASS":
            raise ValueError("E1 predecessor construction audit rejected")
    else:
        original = (case_dir / "input.i").read_text(encoding="utf-8")
    (case_dir / "input.historical.i").write_text(original, encoding="utf-8")
    projected, projection = project_subset_registration_only(original)
    projected = mp.upsert_parameter(projected, "GlobalParams", "enable_jit", "false")
    projected = mp.upsert_parameter(projected, "Outputs", "exodus", "true")
    (case_dir / "input.i").write_text(projected, encoding="utf-8")
    return {
        "historical_sha256": sha256(case_dir / "input.historical.i"),
        "projected_sha256": sha256(case_dir / "input.i"),
        "qvt_mesh_sha256": sha256(case_dir / "qvt.msh"),
        "registration_names_only": projection["status"],
        "JIT_enabled": False,
        "output_exodus": True,
        "not_scientific_parity": True,
    }


def main() -> int:
    result_dir = HERE / "segv_differential_results"
    result_dir.mkdir(exist_ok=True)
    report = {
        "issue": 282,
        "run_class": "CRASH_LOCALIZATION_ONLY",
        "scientific_verdict": "NOT_EVALUATED",
        "source_sha": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "cases": {},
    }
    failures = 0
    def save():
        (result_dir / "manifest.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    for name in CASES:
        case_dir = result_dir / name
        case_dir.mkdir(parents=True, exist_ok=True)
        row = {"status": "STAGING"}
        report["cases"][name] = row
        try:
            row.update(make_case(case_dir, name))
            row["status"] = "STAGED"
            save()
            p2 = run_native(
                case_dir, ["--check-input", "-i", "input.i"],
                log_name="check.log", timeout=PER_CASE_TIMEOUT,
            )
            row["P2_returncode"] = p2
            row["status"] = "P2_PASS" if p2 == 0 else "P2_FAILED"
            save()
            if p2:
                failures += 1
                continue
            p3 = run_native(
                case_dir, ["-i", "input.i"],
                log_name="run.log", timeout=PER_CASE_TIMEOUT,
            )
            row["P3_returncode"] = p3
            row["status"] = (
                "P3_SOLVE_EXECUTED_NOT_SCIENCE_ACCEPTED"
                if p3 == 0 else "P3_SEGFAULT" if p3 in (139, -11)
                else "P3_EXECUTION_FAILED"
            )
            row["evidence_files"] = [
                {"path": p.name, "sha256": sha256(p)}
                for p in sorted(case_dir.iterdir())
                if p.is_file() and (p.suffix in (".csv", ".e", ".log"))
            ]
            failures += int(p3 != 0)
        except Exception as exc:
            row["status"] = "INCONCLUSIVE_DIAGNOSTIC"
            row["error"] = str(exc)
            row["traceback"] = traceback.format_exc()
            failures += 1
        finally:
            save()
    report["status"] = "RESEARCH_DISCRIMINATOR_COMPLETE" if failures == 0 else f"RESEARCH_DISCRIMINATOR_{failures}_NONPASS"
    save()
    print(json.dumps({name: row["status"] for name,row in report["cases"].items()}, sort_keys=True))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
