#!/usr/bin/env python3
"""Issue #477: fail-closed three-case native input manifest for C0-based comparison.

This script prepares overlays only. A separate exact-source native PhysicsApp
P2/P3 execution is required. No private lookup bytes are archived.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

SOURCE_SHA = "29d1acc6ef7969908b86719e4b95c73a1565136d"
PHYSICS_SHA = "8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab"
EI415_SHA256 = "9108838e43298185e71679d2fff09c74c5c601ed3ebbaa3ba02548a374db8c64"
CHEM = Path("experiments/Issue395_powered_chemistry_ladder")
CASES = {
    "S1": ("EI-02", "EI-17"),
    "S2-415": ("EI-02", "EI-17", "EI-415"),
    "S2-417": ("EI-02", "EI-17", "EI-417"),
}
PROGRESS = {
    "EI-02": "R_elastic_O2",
    "EI-17": "R_elastic_O",
    "EI-415": "R_ion_O2",
    "EI-417": "R_EI417",
}
PRIVATE = {"EI-415": "EI-415_O2_X.txt", "EI-417": "EI-417_O2_X.txt"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise ValueError(f"Missing pinned overlay implementation: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_private_rate(path: Path, expected_sha: str | None = None) -> str:
    """Validate the actual table, not a synthesized / fallback rate."""
    if not path.is_file():
        raise ValueError(f"Missing original private chemistry rate: {path.name}")
    digest = sha256(path)
    if expected_sha and digest != expected_sha:
        raise ValueError(f"Wrong pinned rate hash: {path.name}")
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        columns = line.split()
        if len(columns) != 2:
            raise ValueError(f"Non-two-column lookup: {path.name}")
        a, b = [float(c) for c in columns]
        if not (math.isfinite(a) and math.isfinite(b) and b >= 0):
            raise ValueError(f"Nonfinite or negative lookup: {path.name}")
        rows.append((a, b))
    if len(rows) != 100 or any(b[0] <= a[0] for a, b in zip(rows, rows[1:])):
        raise ValueError(f"Wrong 100-row monotonic lookup grid: {path.name}")
    return digest


def verify_inventory(overlays: list[Path], expected: tuple[str, ...]) -> None:
    text = "\n".join(p.read_text() for p in overlays)
    owners = re.findall(r"(?m)^\s*reaction_progress\s*=\s*(R_[A-Za-z0-9_]+)\s*$", text)
    required = [PROGRESS[channel] for channel in expected]
    if sorted(owners) != sorted(required):
        raise ValueError(f"Unexpected active progress owners: found={owners}; expected={required}")
    for name in ("EI-01", "EI-16", "EI-20", "EI-401", "EI-412", "EI-941", "H23", "H24", "H25"):
        if re.search(r"(?m)^\s*(?:reaction_progress|property_name)\s*=\s*R_" + re.escape(name.replace("-", "")) + r"\b", text):
            raise ValueError(f"Unexpected parent chemistry: {name}")
    if len(overlays) != len(expected):
        raise ValueError("Overlay count is inconsistent with requested stage")


def prepare(case: str, private_dir: Path | None = None) -> dict:
    if case not in CASES:
        raise ValueError(f"Unknown case: {case}")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if source != SOURCE_SHA:
        raise ValueError(f"Pinned source mismatch: {source}")

    name = "rf_elastic_diss_ion_ei20_ei01_400w_adjacent_sheath_wall_closed_100us_dt1000ns"
    primary = CHEM / (name + "__C0_chemistry_off.i")
    parent = CHEM / "rf_elastic_multiapp_parent_400w_100us_dt1000ns_overlay.i"
    c0 = CHEM / "c0_400_p2_preflight/c0_manifest.json"
    ei02 = CHEM / "o2_elastic_400w_100us_dt1000ns_overlay.i"
    ei17 = CHEM / "o_elastic_ei17_400w_100us_dt1000ns_overlay.i"
    original_ion = CHEM / "o2_ionization_400w_100us_dt1000ns_overlay.i"

    for path in (primary, parent, c0, ei02, ei17, original_ion):
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"Missing actual staged native input: {path}")

    baseline = json.loads(c0.read_text())
    if (baseline.get("phase") != "P0_STATIC_CANDIDATE_ONLY"
        or baseline.get("source_harness_expected_sha") != SOURCE_SHA
        or baseline.get("physics_app_expected_sha") != PHYSICS_SHA
        or baseline.get("derived_base_sha256") != sha256(primary)
        or baseline.get("expected_steps") != 460
        or len(baseline.get("removed_reactive_wall_objects", [])) != 15
        or baseline.get("power_target_W") != 400):
        raise ValueError("C0 identity, chemistry-off wall or timegrid contract mismatch")

    # The primary/parent must not secretly re-introduce active chemistry progress.
    for path in (primary, parent):
        if re.search(r"(?m)^\s*reaction_progress\s*=", path.read_text()):
            raise ValueError(f"Unexpected inherited chemistry reaction owner: {path}")

    expected = CASES[case]
    overlays = [ei02, ei17]
    lookup_hashes = {}
    if case != "S1":
        channel = expected[-1]
        if private_dir is None:
            raise ValueError("Rate archive required for the electron-generating stage")
        name = PRIVATE[channel]
        private = private_dir / name
        actual_sha = verify_private_rate(private, EI415_SHA256 if channel == "EI-415" else None)
        target_dir = CHEM / "private_rates"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / name
        if target.exists() and sha256(target) != actual_sha:
            raise ValueError("Conflicting existing private rate")
        shutil.copyfile(private, target)
        if sha256(target) != actual_sha:
            raise ValueError("Private rate copy hash mismatch")
        lookup_hashes[channel] = actual_sha
        overlay = CHEM / f"issue477_{case}_generation_overlay.i"
        if overlay.exists():
            raise ValueError("Refuse to overwrite generated chemistry overlay")
        if channel == "EI-415":
            module = load_script(
                Path(".github/scripts/ei415_replaces_ei16_h23_ei401_ei412_ei941_14ch.py"),
                "issue477_ei415_source",
            )
            text = module.transform(original_ion.read_text())
            module.verify_overlay(text)
        else:
            module = load_script(
                Path(".github/scripts/oxygen_legacy8_h05_ei417_100us.py"),
                "issue477_ei417_source",
            )
            text = module.CONTENT
            module.overlay_ok(text)
        overlay.write_text(text)
        overlays.append(overlay)

    # Only these two elastic-energy-exchange overlays plus the case-specific
    # electron-production overlay may be passed to the native solver.
    verify_inventory(overlays, expected)
    output_dir = CHEM / "issue477_first_batch" / case
    if output_dir.exists():
        raise ValueError(f"Refuse to overwrite existing run evidence: {output_dir}")
    (output_dir / "run").mkdir(parents=True)
    (output_dir / "plots").mkdir()
    manifest = {
        "issue": 477, "case": case, "power_W": 400,
        "status": "P0_PREPARED_ONLY", "science_acceptance": "HOLD",
        "source_sha": SOURCE_SHA, "physics_sha": PHYSICS_SHA,
        "chemistry_channels": list(expected),
        "native_timepoint_count_expected": 461,
        "native_steps_expected": 460, "native_end_time_s": 1e-4,
        "input_paths": [str(p) for p in (primary, parent, *overlays)],
        "input_sha256": {str(p): sha256(p) for p in (primary, parent, *overlays)},
        "c0_manifest_sha256": sha256(c0),
        "private_rate_sha256_no_contents": lookup_hashes,
        "reactive_surface_chemistry": "OFF_SAME_AS_C0",
        "fixed_gas_and_transport": "C0_PINNED",
    }
    (output_dir / "case_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print("ISSUE477_FIRST_BATCH_PREPARED", case, expected)
    return manifest


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--case", required=True, choices=CASES)
    p.add_argument("--private-dir", type=Path)
    a = p.parse_args()
    prepare(a.case, a.private_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
