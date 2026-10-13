#!/usr/bin/env python3
"""Issue #376 T6 representative full oxygen-ICP coupling driver.

Sequence:
  full dielectric oxygen plasma (RF source off) -> spatial sigma(r,z)
  -> frequency-domain Maxwell -> conservatively scaled RF source
  -> one recovered full-plasma step -> updated spatial sigma -> Maxwell response.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shlex
import shutil
import subprocess
from pathlib import Path

import numpy as np
from scipy.io import netcdf_file

NA = 6.02214076e23
QE = 1.602176634e-19
ME = 9.1093837015e-31
KB = 1.380649e-23
TG = 300.0
OMEGA = 2.0 * math.pi * 13.56e6
FARADAY = 96485.33212331001
RAW_GATE = 2.0e-2
POWER_GATE = 1.0e-8
SOURCE_UNIT_GATE = 1.0e-8
SIGMA_CV_MIN = 1.0e-3
FEEDBACK_MIN = 1.0e-8
FEEDBACK_MAX = 5.0e-1
STATE_RESPONSE_MIN = 1.0e-8
MAX_TABLE_CLAMP_FRACTION = 5.0e-2


def args():
    p = argparse.ArgumentParser()
    p.add_argument("--physics", required=True)
    p.add_argument("--plasma-input", type=Path, required=True)
    p.add_argument("--plasma-overlay", type=Path, required=True)
    p.add_argument("--maxwell-input", type=Path, required=True)
    p.add_argument("--maxwell-overlay", type=Path, required=True)
    p.add_argument("--table", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--analysis", type=Path, required=True)
    return p.parse_args()


def run(cmd: list[str], log: Path) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as f:
        f.write("$ " + " ".join(shlex.quote(str(x)) for x in cmd) + "\n")
        f.flush()
        r = subprocess.run([str(x) for x in cmd], stdout=f, stderr=subprocess.STDOUT, text=True)
    if r.returncode:
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-120:])
        raise RuntimeError(f"command failed ({r.returncode}): {' '.join(map(str, cmd))}\n{tail}")


def names(var) -> list[str]:
    a = np.asarray(var.data).copy()
    out: list[str] = []
    for row in a:
        if row.dtype.kind == "S":
            s = b"".join(row.tolist()).decode(errors="ignore")
        else:
            s = "".join(chr(int(v)) for v in row if int(v) != 0)
        out.append(s.split("\0")[0].strip())
    return out


def exodus(path: Path) -> dict:
    with netcdf_file(path, "r", mmap=False) as f:
        x = np.asarray(f.variables["coordx"].data, dtype=float).copy()
        y = np.asarray(f.variables["coordy"].data, dtype=float).copy()
        times = np.asarray(f.variables["time_whole"].data, dtype=float).copy()
        eb = names(f.variables["eb_names"])
        blocks: dict[str, np.ndarray] = {}
        bind: dict[str, int] = {}
        for bi, name in enumerate(eb, start=1):
            key = f"connect{bi}"
            if key not in f.variables:
                continue
            conn = np.asarray(f.variables[key].data, dtype=int).copy() - 1
            if conn.ndim == 2 and conn.shape[1] == 3:
                blocks[name] = conn
                bind[name] = bi
        nodal: dict[str, np.ndarray] = {}
        if "name_nod_var" in f.variables:
            nn = names(f.variables["name_nod_var"])
            for vi, name in enumerate(nn, start=1):
                key = f"vals_nod_var{vi}"
                if key in f.variables:
                    nodal[name] = np.asarray(f.variables[key].data, dtype=float).copy()
        elem: dict[str, dict[str, np.ndarray]] = {k: {} for k in blocks}
        if "name_elem_var" in f.variables:
            en = names(f.variables["name_elem_var"])
            for bname, bi in bind.items():
                for vi, vname in enumerate(en, start=1):
                    key = f"vals_elem_var{vi}eb{bi}"
                    if key in f.variables:
                        elem[bname][vname] = np.asarray(f.variables[key].data, dtype=float).copy()
    return {"x": x, "y": y, "times": times, "blocks": blocks, "nodal": nodal, "elem": elem}


def csv_last(path: Path) -> dict[str, float]:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"empty csv: {path}")
    return {k: float(v) for k, v in rows[-1].items() if k and v not in (None, "")}


def table(path: Path) -> tuple[np.ndarray, np.ndarray]:
    a = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        c = s.replace(",", " ").split()
        if len(c) >= 2:
            a.append((float(c[0]), float(c[1])))
    z = np.asarray(a, dtype=float)
    if len(z) < 2 or np.any(np.diff(z[:, 0]) <= 0):
        raise RuntimeError("bad transport table")
    return z[:, 0], z[:, 1]


def p1_eval(points: np.ndarray, triangles: np.ndarray, values: np.ndarray, queries: np.ndarray) -> np.ndarray:
    tri_xy = points[triangles]
    mins = tri_xy.min(axis=1) - 1.0e-12
    maxs = tri_xy.max(axis=1) + 1.0e-12
    out = np.full(len(queries), np.nan)
    for k, p in enumerate(queries):
        cand = np.where((mins[:, 0] <= p[0]) & (p[0] <= maxs[:, 0]) & (mins[:, 1] <= p[1]) & (p[1] <= maxs[:, 1]))[0]
        for idx in cand:
            a, b, c = tri_xy[idx]
            mat = np.array([[a[0], b[0], c[0]], [a[1], b[1], c[1]], [1.0, 1.0, 1.0]])
            lam = np.linalg.solve(mat, np.array([p[0], p[1], 1.0]))
            if lam.min() >= -2e-10 and lam.max() <= 1 + 2e-10:
                out[k] = float(np.dot(lam, values[triangles[idx]]))
                break
    if not np.all(np.isfinite(out)):
        raise RuntimeError(f"P1 interpolation missed {int(np.sum(~np.isfinite(out)))} points")
    return out


def plasma_qstate(pl: dict, tx: np.ndarray, tm: np.ndarray) -> dict:
    tri = pl["blocks"]["plasma"]
    xy = np.column_stack((pl["x"], pl["y"]))
    tri_xy = xy[tri]
    bary = np.array([[1/6, 1/6, 2/3], [1/6, 2/3, 1/6], [2/3, 1/6, 1/6]], dtype=float)
    qpts = (tri_xy[:, None, :, :] * bary[None, :, :, None]).sum(axis=2).reshape(-1, 2)
    logne = pl["nodal"]["log_ne"][-1]
    logue = pl["nodal"]["log_energy"][-1]
    lnq = (logne[tri][:, None, :] * bary[None, :, :]).sum(axis=2).reshape(-1)
    luq = (logue[tri][:, None, :] * bary[None, :, :]).sum(axis=2).reshape(-1)
    if "p" in pl["nodal"]:
        pv = pl["nodal"]["p"][-1]
        pq = (pv[tri][:, None, :] * bary[None, :, :]).sum(axis=2).reshape(-1)
    elif "p" in pl["elem"]["plasma"]:
        pv = pl["elem"]["plasma"]["p"][-1]
        pq = np.repeat(pv, 3)
    else:
        raise RuntimeError("pressure variable p not found in plasma output")
    eps = np.exp(luq - lnq)
    below = eps < tx[0]
    above = eps > tx[-1]
    clamp_frac = float(np.mean(below | above))
    mu_n = np.interp(eps, tx, tm)
    nn = pq / (KB * TG)
    mu = mu_n / nn
    nu = QE / (ME * mu)
    ne = np.exp(lnq) * NA
    den = nu * nu + OMEGA * OMEGA
    sr = ne * QE * QE * nu / (ME * den)
    si = -ne * QE * QE * OMEGA / (ME * den)
    v1 = tri_xy[:, 1] - tri_xy[:, 0]
    v2 = tri_xy[:, 2] - tri_xy[:, 0]
    area = 0.5 * np.abs(v1[:, 0] * v2[:, 1] - v1[:, 1] * v2[:, 0])
    weights = np.repeat(area / 3.0, 3) * 2.0 * math.pi * qpts[:, 0]
    return {"qpts": qpts, "weights": weights, "eps": eps, "sigma_r": sr, "sigma_i": si, "clamp_fraction": clamp_frac}


def mapped_raw_power(plasma_e: Path, maxwell_e: Path, tx: np.ndarray, tm: np.ndarray) -> tuple[float, dict]:
    pl = exodus(plasma_e)
    mw = exodus(maxwell_e)
    qs = plasma_qstate(pl, tx, tm)
    mxy = np.column_stack((mw["x"], mw["y"]))
    mtri = mw["blocks"]["plasma"]
    er = p1_eval(mxy, mtri, mw["nodal"]["E_real"][-1], qs["qpts"])
    ei = p1_eval(mxy, mtri, mw["nodal"]["E_imag"][-1], qs["qpts"])
    q = 0.5 * qs["sigma_r"] * (er * er + ei * ei)
    power = float(np.sum(qs["weights"] * q))
    sr = qs["sigma_r"]
    stats = {
        "mean_energy_min_eV": float(np.min(qs["eps"])),
        "mean_energy_max_eV": float(np.max(qs["eps"])),
        "table_clamp_fraction": qs["clamp_fraction"],
        "sigma_real_min_S_per_m": float(np.min(sr)),
        "sigma_real_max_S_per_m": float(np.max(sr)),
        "sigma_real_mean_S_per_m": float(np.mean(sr)),
        "sigma_real_cv": float(np.std(sr) / max(abs(np.mean(sr)), 1e-300)),
    }
    return power, stats


def rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-300)


def main() -> int:
    a = args()
    out = a.output_dir.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    analysis = a.analysis.resolve()
    report = {"issue": 376, "gate": "T6 representative full oxygen ICP", "status": "ERROR", "failures": []}
    try:
        physics = str(Path(a.physics).resolve())
        pin = str(a.plasma_input.resolve())
        pov = str(a.plasma_overlay.resolve())
        minp = str(a.maxwell_input.resolve())
        mov = str(a.maxwell_overlay.resolve())
        tx, tm = table(a.table)

        seed = out / "seed" / "maxwell"
        run([physics, "-i", minp, f"Outputs/file_base={seed}"], out / "seed" / "maxwell.log")
        seed_e = seed.with_suffix(".e")
        if not seed_e.is_file():
            raise RuntimeError("seed Maxwell Exodus missing")

        pbase = out / "bootstrap" / "plasma"
        common_plasma = [physics, "-i", pin, pov]
        run(common_plasma + [f"maxwell_solution_file_t6={seed_e}", "source_enable_t6=0", "rf_scale_t6=1", f"Outputs/file_base={pbase}", "--check-input"], out / "bootstrap" / "check.log")
        run(common_plasma + [f"maxwell_solution_file_t6={seed_e}", "source_enable_t6=0", "rf_scale_t6=1", f"Outputs/file_base={pbase}"], out / "bootstrap" / "run.log")
        pe = pbase.with_suffix(".e")
        pcsv = pbase.with_suffix(".csv")
        if not pe.is_file() or not pcsv.is_file():
            raise RuntimeError("bootstrap plasma output missing")
        state100 = out / "bootstrap" / "state100ns.e"
        csv100 = out / "bootstrap" / "state100ns.csv"
        shutil.copy2(pe, state100)
        shutil.copy2(pcsv, csv100)

        m1 = out / "maxwell1" / "maxwell"
        run([physics, "-i", minp, mov, f"plasma_solution_file_t6={state100}", f"Outputs/file_base={m1}", "--check-input"], out / "maxwell1" / "check.log")
        run([physics, "-i", minp, mov, f"plasma_solution_file_t6={state100}", f"Outputs/file_base={m1}"], out / "maxwell1" / "run.log")
        m1e = m1.with_suffix(".e")
        m1csv = m1.with_suffix(".csv")
        pabs1 = csv_last(m1csv)["P_abs"]
        raw, s0 = mapped_raw_power(state100, m1e, tx, tm)
        if not (raw > 0 and pabs1 > 0):
            raise RuntimeError("non-positive T6 RF power")
        scale = pabs1 / raw
        (out / "scale.json").write_text(json.dumps({"Maxwell_P_abs_W": pabs1, "mapped_raw_W": raw, "raw_relative_defect": rel(raw, pabs1), "rf_scale": scale, "state": s0}, indent=2) + "\n", encoding="utf-8")

        run(common_plasma + [f"maxwell_solution_file_t6={m1e}", "source_enable_t6=1", f"rf_scale_t6={scale:.17g}", "Executioner/end_time=1.01e-7", "Executioner/num_steps=101", f"Outputs/file_base={pbase}", "--recover"], out / "source_on_recover.log")
        state101 = out / "state101ns.e"
        csv101 = out / "state101ns.csv"
        shutil.copy2(pe, state101)
        shutil.copy2(pcsv, csv101)

        m2 = out / "maxwell2" / "maxwell"
        run([physics, "-i", minp, mov, f"plasma_solution_file_t6={state101}", f"Outputs/file_base={m2}"], out / "maxwell2" / "run.log")
        m2e = m2.with_suffix(".e")
        m2csv = m2.with_suffix(".csv")
        c1 = csv_last(m1csv)
        c2 = csv_last(m2csv)
        pf = csv_last(csv101)
        pabs2 = c2["P_abs"]
        pscaled = pf["P_rf_scaled_W_t6"]
        praw_moose = pf["P_rf_raw_W_t6"]
        source_evmol = pf["S_rf_eV_mol_s_t6"]

        st0 = exodus(state100)
        st1 = exodus(state101)
        e0 = np.exp(st0["nodal"]["log_energy"][-1] - st0["nodal"]["log_ne"][-1])
        e1 = np.exp(st1["nodal"]["log_energy"][-1] - st1["nodal"]["log_ne"][-1])
        energy_response = float(np.linalg.norm(e1 - e0) / max(np.linalg.norm(e0), 1e-300))
        field1 = math.hypot(c1["E_real_l2"], c1["E_imag_l2"])
        field2 = math.hypot(c2["E_real_l2"], c2["E_imag_l2"])
        power_feedback = rel(pabs2, pabs1)
        field_feedback = rel(field2, field1)
        raw_defect = rel(raw, pabs1)
        closure = rel(pscaled, pabs1)
        source_unit = rel(source_evmol * FARADAY, pscaled)

        required_nodal = {"log_ne", "log_energy", "potential"}
        required_elem = {"log_ni", "log_nm", "log_nop", "p", "w_O", "w_O2s", "w_Os"}
        nodal_ok = required_nodal.issubset(st1["nodal"])
        elem_ok = required_elem.issubset(st1["elem"].get("plasma", {}))
        finite_positive = bool(np.all(np.isfinite(e1)) and np.all(e1 > 0) and np.all(np.isfinite(st1["nodal"]["log_ne"][-1])))
        input_text = a.plasma_input.read_text(encoding="utf-8")
        overlay_text = a.plasma_overlay.read_text(encoding="utf-8")
        dielectric_tokens = ["eps_cover", "eps_wafer", "eps_focus_ring", "eps_vacuum", "sigma_s", "sigma_wafer", "sigma_focus_ring", "PhysicsADSurfaceChargePoissonBC"]
        dielectric_ok = all(t in input_text for t in dielectric_tokens)
        separate_owners = ("PhysicsFEMLogMolarElectronJouleHeating" in input_text and overlay_text.count("material_property = q_rf_eV_mol_t6") == 1)

        failures: list[str] = []
        if raw_defect > RAW_GATE: failures.append(f"raw remesh power defect {raw_defect:.6e} > {RAW_GATE:.6e}")
        if closure > POWER_GATE: failures.append(f"deposited RF power closure {closure:.6e} > {POWER_GATE:.6e}")
        if source_unit > SOURCE_UNIT_GATE: failures.append(f"RF source unit closure {source_unit:.6e} > {SOURCE_UNIT_GATE:.6e}")
        if s0["sigma_real_cv"] < SIGMA_CV_MIN: failures.append(f"spatial sigma CV {s0['sigma_real_cv']:.6e} < {SIGMA_CV_MIN:.6e}")
        if s0["table_clamp_fraction"] > MAX_TABLE_CLAMP_FRACTION: failures.append(f"transport-table clamp fraction {s0['table_clamp_fraction']:.6e} > {MAX_TABLE_CLAMP_FRACTION:.6e}")
        if not (FEEDBACK_MIN < power_feedback < FEEDBACK_MAX): failures.append(f"Maxwell power feedback response {power_feedback:.6e} outside ({FEEDBACK_MIN:.6e},{FEEDBACK_MAX:.6e})")
        if field_feedback <= FEEDBACK_MIN: failures.append(f"Maxwell field did not respond: {field_feedback:.6e}")
        if energy_response <= STATE_RESPONSE_MIN: failures.append(f"electron-energy state did not respond: {energy_response:.6e}")
        if not nodal_ok: failures.append("required FEM plasma variables missing")
        if not elem_ok: failures.append("required oxygen/FV plasma variables missing")
        if not finite_positive: failures.append("non-finite/non-positive electron state")
        if not dielectric_ok: failures.append("full dielectric/surface-charge contract missing")
        if not separate_owners: failures.append("RF/electrostatic electron-heating ownership is not separated")

        report = {
            "issue": 376,
            "gate": "T6 representative full oxygen ICP",
            "status": "PASS" if not failures else "FAIL",
            "scope": "100 ns full dielectric oxygen-plasma bootstrap; one 1 ns recovered RF-heated full-physics step; spatial plasma state -> frequency-domain Maxwell -> conservative RF source -> updated plasma -> Maxwell feedback.",
            "standard_moose_only": True,
            "custom_cpp_added": False,
            "state100ns": s0,
            "rf_transfer": {"Maxwell_P_abs_W": pabs1, "independent_target_raw_W": raw, "raw_relative_defect": raw_defect, "rf_scale": scale, "MOOSE_target_raw_W": praw_moose, "MOOSE_target_scaled_W": pscaled, "deposited_relative_closure": closure, "source_eV_mol_s": source_evmol, "source_unit_relative_closure": source_unit},
            "feedback": {"Maxwell1_P_abs_W": pabs1, "Maxwell2_P_abs_W": pabs2, "power_relative_change": power_feedback, "Maxwell1_field_l2": field1, "Maxwell2_field_l2": field2, "field_relative_change": field_feedback, "electron_mean_energy_field_relative_change": energy_response},
            "full_physics": {"required_nodal_variables_present": nodal_ok, "required_oxygen_FV_variables_present": elem_ok, "electron_state_finite_positive": finite_positive, "dielectric_surface_charge_contract_present": dielectric_ok, "RF_and_electrostatic_heating_separate": separate_owners},
            "tolerances": {"raw_mapping_relative": RAW_GATE, "power_relative": POWER_GATE, "source_unit_relative": SOURCE_UNIT_GATE, "sigma_cv_min": SIGMA_CV_MIN, "feedback_min": FEEDBACK_MIN, "feedback_max": FEEDBACK_MAX, "state_response_min": STATE_RESPONSE_MIN, "max_table_clamp_fraction": MAX_TABLE_CLAMP_FRACTION},
            "failures": failures,
        }
        analysis.parent.mkdir(parents=True, exist_ok=True)
        analysis.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("T6_REPRESENTATIVE_ICP_" + report["status"])
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if not failures else 1
    except Exception as exc:
        report["status"] = "ERROR"
        report["failures"] = [f"runtime: {exc}"]
        report["exception"] = repr(exc)
        analysis.parent.mkdir(parents=True, exist_ok=True)
        analysis.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"T6_REPRESENTATIVE_ICP_ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
