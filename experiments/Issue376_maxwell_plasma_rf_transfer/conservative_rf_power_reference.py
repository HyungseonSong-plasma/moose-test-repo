#!/usr/bin/env python3
"""Issue #376 T1 conservative RF-power transfer oracle.

Given a scalar-RZ P1 Maxwell Exodus result, reconstruct the exact element-wise
RF power for the plasma block and the conservative cell-average source.

For a linear triangular element:
    E_h = sum_i E_i lambda_i
    r   = sum_i r_i lambda_i
and Q_RF = 0.5*sigma_R*|E_h|^2.  The RZ element power is
    P_K = 2*pi * integral_A r Q_RF dA.
The polynomial r*|E_h|^2 has total degree 3, so we integrate it analytically
with barycentric moments.  The conservative cell average is
    Q_K = P_K / V_K,
    V_K = 2*pi * integral_A r dA.
Thus sum_K Q_K V_K == sum_K P_K by construction.

The same power can be expressed in the canonical log-molar electron-energy
units by S_RF = Q_RF/F, where F = N_A*e [J/(V mol)] and numerically one volt
of singly-charged-particle work corresponds to one eV per particle.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file

AVOGADRO = 6.02214076e23
ELEMENTARY_CHARGE_C = 1.602176634e-19
FARADAY_C_PER_MOL = AVOGADRO * ELEMENTARY_CHARGE_C


def _decode_names(var) -> list[str]:
    arr = np.asarray(var.data).copy()
    out: list[str] = []
    for row in arr:
        raw = b"".join(row.tolist()) if row.dtype.kind == "S" else bytes(row)
        out.append(raw.decode(errors="ignore").split("\x00", 1)[0].strip())
    return out


def _triangle_area(r: np.ndarray, z: np.ndarray) -> float:
    return 0.5 * abs(
        (r[1] - r[0]) * (z[2] - z[0]) - (r[2] - r[0]) * (z[1] - z[0])
    )


def _barycentric_moment(area: float, counts: tuple[int, int, int]) -> float:
    """Integral(lambda_0^a lambda_1^b lambda_2^c dA) on one triangle."""
    degree = sum(counts)
    numer = 2.0 * area
    for count in counts:
        numer *= math.factorial(count)
    return numer / math.factorial(degree + 2)


def _integral_r_times_linear_squared(
    r: np.ndarray, z: np.ndarray, nodal: np.ndarray
) -> float:
    area = _triangle_area(r, z)
    total = 0.0
    for k in range(3):
        for i in range(3):
            for j in range(3):
                counts = [0, 0, 0]
                counts[k] += 1
                counts[i] += 1
                counts[j] += 1
                total += (
                    r[k]
                    * nodal[i]
                    * nodal[j]
                    * _barycentric_moment(area, tuple(counts))
                )
    return total


def _load_exodus(path: Path, block_name: str):
    with netcdf_file(path, "r", mmap=False) as f:
        r = np.asarray(f.variables["coordx"].data, dtype=float).copy()
        z = np.asarray(f.variables["coordy"].data, dtype=float).copy()

        block_names = _decode_names(f.variables["eb_names"])
        if block_name not in block_names:
            raise RuntimeError(
                f"block {block_name!r} not present; available={block_names}"
            )
        block_index = block_names.index(block_name) + 1
        conn = np.asarray(
            f.variables[f"connect{block_index}"].data, dtype=int
        ).copy() - 1
        if conn.ndim != 2 or conn.shape[1] != 3:
            raise RuntimeError(
                f"T1 oracle currently requires TRI3 elements; got {conn.shape}"
            )

        nodal_names = _decode_names(f.variables["name_nod_var"])
        values = {}
        for index, name in enumerate(nodal_names, start=1):
            key = f"vals_nod_var{index}"
            values[name] = np.asarray(f.variables[key].data[-1], dtype=float).copy()

    for required in ("E_real", "E_imag"):
        if required not in values:
            raise RuntimeError(
                f"required nodal variable {required!r} absent; available={nodal_names}"
            )
    return r, z, conn, values["E_real"], values["E_imag"]


def _load_moose_power(csv_path: Path | None) -> float | None:
    if csv_path is None:
        return None
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or "P_abs" not in rows[-1]:
        raise RuntimeError(f"P_abs not found in {csv_path}")
    return float(rows[-1]["P_abs"])


def analyze(
    exodus: Path,
    sigma_r: float,
    block_name: str = "plasma",
    moose_csv: Path | None = None,
):
    r, z, conn, e_real, e_imag = _load_exodus(exodus, block_name)

    rows = []
    exact_total = 0.0
    centroid_total = 0.0
    volume_total = 0.0

    for local_id, nodes in enumerate(conn):
        rr = r[nodes]
        zz = z[nodes]
        area = _triangle_area(rr, zz)
        volume = 2.0 * math.pi * area * float(np.mean(rr))
        if volume <= 0.0:
            raise RuntimeError(f"non-positive RZ volume on plasma element {local_id}")

        int_r_er2 = _integral_r_times_linear_squared(rr, zz, e_real[nodes])
        int_r_ei2 = _integral_r_times_linear_squared(rr, zz, e_imag[nodes])
        power = 0.5 * sigma_r * 2.0 * math.pi * (int_r_er2 + int_r_ei2)
        q_cell = power / volume
        source_molar = q_cell / FARADAY_C_PER_MOL

        # Deliberately non-conservative negative mutation: evaluate the P1 field
        # at the triangle centroid and multiply by exact RZ cell volume.
        er_centroid = float(np.mean(e_real[nodes]))
        ei_centroid = float(np.mean(e_imag[nodes]))
        q_centroid = 0.5 * sigma_r * (
            er_centroid * er_centroid + ei_centroid * ei_centroid
        )
        centroid_power = q_centroid * volume

        exact_total += power
        centroid_total += centroid_power
        volume_total += volume
        rows.append(
            {
                "cell": local_id,
                "volume_m3": volume,
                "power_W": power,
                "q_rf_cell_W_m3": q_cell,
                "rf_energy_source_eV_mol_m3_s": source_molar,
            }
        )

    reconstructed = sum(row["q_rf_cell_W_m3"] * row["volume_m3"] for row in rows)
    reconstructed_from_energy = sum(
        row["rf_energy_source_eV_mol_m3_s"]
        * FARADAY_C_PER_MOL
        * row["volume_m3"]
        for row in rows
    )
    scale = max(abs(exact_total), 1.0)
    conservative_rel = abs(reconstructed - exact_total) / scale
    energy_rel = abs(reconstructed_from_energy - exact_total) / scale

    moose_power = _load_moose_power(moose_csv)
    moose_rel = (
        None
        if moose_power is None
        else abs(exact_total - moose_power) / max(abs(moose_power), 1.0)
    )
    centroid_rel = (
        0.0
        if exact_total == 0.0
        else abs(centroid_total - exact_total) / abs(exact_total)
    )

    report = {
        "issue": 376,
        "gate": "T1 conservative RF-power transfer oracle",
        "representation": {
            "maxwell": "P1 continuous FEM",
            "oracle": "exact TRI3 cell integral with RZ 2*pi*r weight",
            "cell_source": "piecewise-constant conservative average",
            "electron_energy_unit_conversion": "S_RF[eV mol/(m^3 s)] = Q_RF[W/m^3]/F",
        },
        "input": {
            "exodus": str(exodus),
            "block": block_name,
            "sigma_r_S_m": sigma_r,
            "plasma_cells": len(rows),
        },
        "power": {
            "exact_fe_integral_W": exact_total,
            "conservative_cell_sum_W": reconstructed,
            "energy_source_reconstructed_W": reconstructed_from_energy,
            "conservative_relative_closure": conservative_rel,
            "energy_unit_relative_closure": energy_rel,
            "moose_P_abs_W": moose_power,
            "moose_relative_mismatch": moose_rel,
            "centroid_negative_mutation_W": centroid_total,
            "centroid_negative_mutation_relative_mismatch": centroid_rel,
        },
        "plasma_volume_m3": volume_total,
        "faraday_C_per_mol": FARADAY_C_PER_MOL,
        "cell_source_range_W_m3": [
            min(row["q_rf_cell_W_m3"] for row in rows),
            max(row["q_rf_cell_W_m3"] for row in rows),
        ],
    }
    return report, rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exodus", type=Path, required=True)
    parser.add_argument("--sigma-r", type=float, required=True)
    parser.add_argument("--block", default="plasma")
    parser.add_argument("--moose-csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cells-csv", type=Path)
    parser.add_argument("--closure-tol", type=float, default=1.0e-12)
    parser.add_argument("--moose-tol", type=float, default=1.0e-10)
    parser.add_argument("--require-centroid-discriminator", action="store_true")
    args = parser.parse_args()

    report, rows = analyze(
        args.exodus, args.sigma_r, block_name=args.block, moose_csv=args.moose_csv
    )

    failures = []
    power = report["power"]
    if power["conservative_relative_closure"] > args.closure_tol:
        failures.append("conservative cell-average closure failed")
    if power["energy_unit_relative_closure"] > args.closure_tol:
        failures.append("electron-energy unit conversion closure failed")
    if (
        power["moose_relative_mismatch"] is not None
        and power["moose_relative_mismatch"] > args.moose_tol
    ):
        failures.append("independent exact FE integral disagrees with MOOSE P_abs")
    if (
        args.require_centroid_discriminator
        and abs(power["exact_fe_integral_W"]) > 0.0
        and power["centroid_negative_mutation_relative_mismatch"] <= 1.0e-6
    ):
        failures.append("centroid negative mutation did not discriminate")

    report["tolerances"] = {
        "closure_relative": args.closure_tol,
        "moose_relative": args.moose_tol,
    }
    report["status"] = "FAIL" if failures else "PASS"
    report["failures"] = failures

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    if args.cells_csv is not None:
        args.cells_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.cells_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
