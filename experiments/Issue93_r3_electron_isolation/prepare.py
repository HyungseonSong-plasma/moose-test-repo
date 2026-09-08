#!/usr/bin/env python3
"""Prepare Issue #93 J1 from the accepted Issue #2 real-QVT electron case."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE_CASE = ROOT / "experiments" / "Issue91_real_qvt_r3" / "r3_e0"
ELECTRON_REFERENCE_CASE = ROOT / "experiments" / "Issue2_electron_bulk_drift" / "qvt_prepoisson"
DEFAULT_DT = 1.0e-8
P_FROZEN = 1.33322
TG_FROZEN = 600.0
NE_INITIAL = 1.0e16
EXPECTED_MESH_SHA256 = "a98521af2c106137f9635fe7e2c5ba9b0fd408e17c62eb7c6d3f7c1fff65a03e"


class PrepareError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _replace_exact_once(text: str, old: str, new: str, claim: str) -> str:
    count = text.count(old)
    if count != 1:
        raise PrepareError(f"{claim}: expected exactly one {old!r}, found {count}")
    return text.replace(old, new, 1)


def _assignment(text: str, name: str) -> float:
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*=\s*([^#\s]+)", text)
    if not match:
        raise PrepareError(f"missing assignment {name}")
    return float(match.group(1))


def build_input(
    electron_reference_case: Path = ELECTRON_REFERENCE_CASE,
    dt: float = DEFAULT_DT,
) -> str:
    """Return the accepted #2 qvt input with only the prescribed field changed to zero."""
    if not dt > 0:
        raise PrepareError("dt must be positive")
    reference = (electron_reference_case / "input.i").read_text()
    accepted_dt = _assignment(reference, "dt")
    if abs(accepted_dt - dt) > 1.0e-30:
        raise PrepareError(
            f"J1 dt must remain the accepted #2 value {accepted_dt:.17g}; requested {dt:.17g}"
        )
    candidate = _replace_exact_once(
        reference,
        "expression = '-0.01*x'",
        "expression = '0.0*x'",
        "zero-field discriminator",
    )
    if candidate == reference:
        raise PrepareError("zero-field discriminator produced no semantic diff")
    return (
        "# Issue #93 J1: direct derivative of accepted Issue2 qvt_prepoisson.\n"
        "# Only scientific discriminator change: prescribed E 0.01 V/m -> 0 V/m.\n"
        + candidate
    )


def prepare_case(
    dest: Path,
    r3_source_case: Path = SOURCE_CASE,
    dt: float = DEFAULT_DT,
    electron_reference_case: Path = ELECTRON_REFERENCE_CASE,
) -> dict[str, Any]:
    r3_source_case = r3_source_case.resolve()
    electron_reference_case = electron_reference_case.resolve()
    dest = dest.resolve()

    required_reference = ("input.i", "qvt.msh", "electron_moments.txt")
    for name in required_reference:
        if not (electron_reference_case / name).is_file():
            raise PrepareError(f"missing accepted #2 reference asset: {electron_reference_case / name}")
    for name in ("qvt.msh", "electron_moments.txt"):
        if not (r3_source_case / name).is_file():
            raise PrepareError(f"missing Issue91 identity asset: {r3_source_case / name}")

    ref_mesh_sha = _sha256(electron_reference_case / "qvt.msh")
    r3_mesh_sha = _sha256(r3_source_case / "qvt.msh")
    if ref_mesh_sha != r3_mesh_sha:
        raise PrepareError(f"real-qvt mesh identity mismatch: #2={ref_mesh_sha} #91={r3_mesh_sha}")
    if ref_mesh_sha != EXPECTED_MESH_SHA256:
        raise PrepareError(f"unexpected qvt mesh identity: {ref_mesh_sha}")

    ref_table_sha = _sha256(electron_reference_case / "electron_moments.txt")
    r3_table_sha = _sha256(r3_source_case / "electron_moments.txt")
    if ref_table_sha != r3_table_sha:
        raise PrepareError(
            f"electron table identity mismatch: #2={ref_table_sha} #91={r3_table_sha}"
        )

    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(electron_reference_case / "qvt.msh", dest / "qvt.msh")
    shutil.copy2(electron_reference_case / "electron_moments.txt", dest / "electron_moments.txt")
    input_text = build_input(electron_reference_case, dt)
    (dest / "input.i").write_text(input_text)

    reference_text = (electron_reference_case / "input.i").read_text()
    evidence = {
        "issue": 93,
        "stage": "J1_PREPARE",
        "scientific_acceptance_eligible": False,
        "r3_source_case": str(r3_source_case),
        "electron_reference_case": str(electron_reference_case),
        "reference_input_sha256": hashlib.sha256(reference_text.encode()).hexdigest(),
        "candidate_input_sha256": hashlib.sha256(input_text.encode()).hexdigest(),
        "dt_s": dt,
        "accepted_reference_end_time_s": _assignment(reference_text, "end_time"),
        "p_frozen_Pa": P_FROZEN,
        "T_g_frozen_K": TG_FROZEN,
        "n_e_initial_m3": NE_INITIAL,
        "field_change": "accepted #2 phi=-0.01*x -> J1 phi=0.0*x",
        "heavy_nonlinear_equations": "ABSENT_IN_ACCEPTED_ISSUE2_REFERENCE",
        "poisson": "OFF",
        "electron_contract": "DIRECT_ACCEPTED_ISSUE2_QVT_PREPOISSON_DERIVATIVE",
        "mesh_sha256": ref_mesh_sha,
        "electron_table_sha256": ref_table_sha,
        "semantic_diff_count": 1,
    }
    (dest / "prepare_evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--source-case", type=Path, default=SOURCE_CASE)
    parser.add_argument("--electron-reference-case", type=Path, default=ELECTRON_REFERENCE_CASE)
    parser.add_argument("--dt", type=float, default=DEFAULT_DT)
    args = parser.parse_args()
    try:
        evidence = prepare_case(
            args.dest,
            args.source_case,
            args.dt,
            args.electron_reference_case,
        )
    except (PrepareError, OSError, ValueError) as exc:
        print(f"ISSUE93_J1_PREPARE_ERROR: {exc}")
        return 2
    print(json.dumps(evidence, indent=2, sort_keys=True))
    print("ISSUE93_J1_PREPARE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
