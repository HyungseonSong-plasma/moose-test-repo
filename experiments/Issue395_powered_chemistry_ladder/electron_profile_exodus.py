"""Issue 457: lossless-location electron-state sampling from native Exodus.

No interpolation or field-oracle claim. Accepts only the actual solved log-state
variables and source-attributable native time/mesh identities.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file

from experiments.Issue395_powered_chemistry_ladder.chemistry_off_c0 import (
    EXPECTED_SOURCE, EXPECTED_PHYSICS, expected_grid_ns,
)

N_A = 6.02214076e23
SAMPLES_US = (0, 0.1, 1, 2, 10, 25, 50, 75, 100)


class ElectronProfileError(ValueError):
    pass


def _names(variable: np.ndarray) -> list[str]:
    return [b"".join(bytes(v) for v in row).decode("utf-8", "replace").strip("\x00 ").strip()
            for row in variable]


def _coord(f, key: str, dimension: int) -> np.ndarray:
    if key in f.variables:
        return np.asarray(f.variables[key][:], dtype=float).copy()
    if "coord" in f.variables:
        return np.asarray(f.variables["coord"][dimension, :], dtype=float).copy()
    raise ElectronProfileError(f"missing Exodus coordinate: {key}")


def extract(exodus: Path, c0_manifest: Path, output_dir: Path) -> dict:
    exodus, c0_manifest, output_dir = exodus.resolve(strict=True), c0_manifest.resolve(strict=True), output_dir.resolve(strict=False)
    if not exodus.is_file():
        raise ElectronProfileError("native Exodus file missing")
    if output_dir.exists():
        raise ElectronProfileError("refuse to overwrite existing profile evidence directory")
    manifest = json.loads(c0_manifest.read_text(encoding="utf-8"))
    if (manifest.get("phase") != "P0_STATIC_CANDIDATE_ONLY" or
            manifest.get("source_harness_expected_sha") != EXPECTED_SOURCE or
            manifest.get("physics_app_expected_sha") != EXPECTED_PHYSICS or
            manifest.get("active_cli_input_files") is None or
            len(manifest["active_cli_input_files"]) != 2 or
            manifest.get("power_target_W") != 400):
        raise ElectronProfileError("wrong C0 source identity or manifest class")
    with netcdf_file(str(exodus), "r", mmap=False) as f:
        if "time_whole" not in f.variables:
            raise ElectronProfileError("missing native time_whole")
        times = np.asarray(f.variables["time_whole"][:], dtype=float).copy()
        expected = np.asarray(expected_grid_ns(), dtype=float) * 1e-9
        if times.shape != expected.shape or not np.all(np.isfinite(times)) or np.max(np.abs(times - expected)) > 1e-13:
            raise ElectronProfileError("native Exodus does not have the exact 0–100us / 460-step timeline")
        r, z = _coord(f, "coordx", 0), _coord(f, "coordy", 1)
        if r.shape != z.shape or not np.all(np.isfinite(r)) or not np.all(np.isfinite(z)) or np.any(r < -1e-12):
            raise ElectronProfileError("invalid 2D RZ Exodus coordinates")
        if "eb_names" not in f.variables:
            raise ElectronProfileError("native Exodus has no element-block names; plasma membership unknown")
        blocks = _names(np.asarray(f.variables["eb_names"][:]).copy())
        if blocks.count("plasma") != 1:
            raise ElectronProfileError(f"expected exactly one plasma element block, got {blocks}")
        block_index = blocks.index("plasma") + 1
        conn_name = f"connect{block_index}"
        if conn_name not in f.variables:
            raise ElectronProfileError(f"missing plasma connectivity: {conn_name}")
        conn = np.asarray(f.variables[conn_name][:], dtype=int).copy()
        if conn.ndim != 2 or conn.shape[1] < 3 or conn.size == 0 or np.any(conn < 1) or np.any(conn > len(r)):
            raise ElectronProfileError("invalid 1-based plasma connectivity")
        indices = np.unique(conn.ravel() - 1)
        if "name_nod_var" not in f.variables:
            raise ElectronProfileError("missing native nodal fields; no guessed derived profile")
        names = _names(np.asarray(f.variables["name_nod_var"][:]).copy())
        if names.count("log_ne") != 1 or names.count("log_energy") != 1:
            raise ElectronProfileError(f"native nodal log_ne/log_energy missing or duplicated: {names}")
        def field(name: str) -> np.ndarray:
            variable_name = f"vals_nod_var{names.index(name) + 1}"
            if variable_name not in f.variables:
                raise ElectronProfileError(f"missing native variable {variable_name}")
            arr = np.asarray(f.variables[variable_name][:], dtype=float).copy()
            if arr.shape != (len(times), len(r)):
                raise ElectronProfileError(f"wrong native field shape: {name} {arr.shape}")
            return arr[:, indices]
        log_ne, log_energy = field("log_ne"), field("log_energy")
        if not np.all(np.isfinite(log_ne)) or not np.all(np.isfinite(log_energy)):
            raise ElectronProfileError("non-finite native solved electron state")
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        electron_density = N_A * np.exp(log_ne)
        mean_en = np.exp(log_energy - log_ne)
    if not np.all(np.isfinite(electron_density)) or not np.all(np.isfinite(mean_en)) or np.any(mean_en <= 0):
        raise ElectronProfileError("invalid converted electron state or mean energy")
    sample_indices = []
    for time_us in SAMPLES_US:
        matches = np.flatnonzero(abs(times - time_us * 1e-6) <= 1e-13)
        if len(matches) != 1:
            raise ElectronProfileError(f"exact time sample not available: {time_us} us")
        sample_indices.append(int(matches[0]))
    output_dir.mkdir(parents=True, exist_ok=False)
    csv_path = output_dir / "electron_profile_2d.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("time_us", "node_id_1based", "r_m", "z_m", "n_e_m3", "mean_energy_eV", "T_e_eV"))
        for step, time_us in zip(sample_indices, SAMPLES_US):
            for j, node_idx in enumerate(indices):
                writer.writerow((f"{time_us:.10g}", int(node_idx) + 1,
                                 f"{r[node_idx]:.17g}", f"{z[node_idx]:.17g}",
                                 f"{electron_density[step,j]:.17g}",
                                 f"{mean_en[step,j]:.17g}",
                                 f"{(2/3)*mean_en[step,j]:.17g}"))
    summary = {
        "issue": 457, "status": "NATIVE_EXODUS_FIELDS_EXTRACTED_NOT_SCIENCE_PASS",
        "exodus_sha256": hashlib.sha256(exodus.read_bytes()).hexdigest(),
        "c0_manifest_sha256": hashlib.sha256(c0_manifest.read_bytes()).hexdigest(),
        "plasma_node_count": int(len(indices)), "samples_us": list(SAMPLES_US),
        "timepoint_count": len(times), "fields": ["log_ne", "log_energy"],
        "electron_density_units": "m^-3", "electron_mean_energy_units": "eV",
        "science_acceptance": "HOLD", "checkerboard_decision": "NOT_EVALUATED",
        "observations": [
            {"time_us": time_us,
             "ne_min_m3": float(electron_density[step].min()),
             "ne_max_m3": float(electron_density[step].max()),
             "ne_zero_fraction": float(np.mean(electron_density[step] == 0)),
             "mean_energy_min_eV": float(mean_en[step].min()),
             "mean_energy_max_eV": float(mean_en[step].max())}
            for step, time_us in zip(sample_indices, SAMPLES_US)
        ],
    }
    (output_dir / "profile_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="physics oxygen-profile")
    parser.add_argument("--exodus", type=Path, required=True)
    parser.add_argument("--c0-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = extract(args.exodus, args.c0_manifest, args.output_dir)
    except (ElectronProfileError, ValueError, OSError, KeyError) as exc:
        print(f"OXYGEN_PROFILE: HOLD ({exc})")
        return 2
    print(f"OXYGEN_PROFILE: OBSERVED_ONLY nodes={summary['plasma_node_count']}")
    print(f"PROFILE_SUMMARY={args.output_dir / 'profile_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
