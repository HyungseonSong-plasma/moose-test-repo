#!/usr/bin/env python3
"""Issue #397 D1 native, per-face early sheath/current diagnostic.

Only solver-native lower-D element fields count as evidence; records the
sampled physical face flux constituents, sheath-drop functor, and sided
element-field reconstruction. A diagnostic PASS is NOT sheath/physics PASS.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import numpy as np
from scipy.io import netcdf_file

E = 1.602176634e-19
FIELDS = (
    "sigma_wafer", "wafer_net_current_probe",
    "d1_gamma_o2_positive", "d1_gamma_o_positive", "d1_gamma_o_negative",
    "d1_gamma_electron", "d1_sheath_drop_V", "d1_ne_m3",
    "d1_mean_energy_eV", "d1_electron_mean_speed_m_s",
    "d1_normal_r", "d1_normal_z", "d1_owner", "d1_d_perp_m", "d1_e_n_V_m",
)


def names(rows):
    return [bytes(x).decode("utf8", "replace").strip("\x00 ").strip() for x in rows]


def load_native_exodus(path):
    with netcdf_file(str(path), "r", mmap=False) as f:
        times = np.asarray(f.variables["time_whole"][:], float).copy()
        eb = names(f.variables["eb_names"][:]).index("wafer_surface") + 1
        variables = names(f.variables["name_elem_var"][:])
        conn = np.asarray(f.variables[f"connect{eb}"][:], int).copy() - 1
        if "coordx" in f.variables:
            rcoords = np.asarray(f.variables["coordx"][:], float).copy()
        elif "coord" in f.variables:
            rcoords = np.asarray(f.variables["coord"][:], float).copy()[0]
        else:
            raise ValueError("Neither Exodus coordx nor coord exists")
        endpoints = rcoords[conn]
        rmin = endpoints.min(axis=1)
        rmax = endpoints.max(axis=1)
        radius = endpoints.mean(axis=1)
        pos = np.argsort(radius)
        data = {}
        for name in FIELDS:
            if name not in variables:
                raise RuntimeError(f"Missing solver-native Exodus field {name}; found {variables}")
            var = f"vals_elem_var{variables.index(name)+1}eb{eb}"
            if var not in f.variables:
                raise RuntimeError(f"Missing solver-native Exodus variable {var}")
            data[name] = np.asarray(f.variables[var][:], float).copy()[:, pos]
    n_faces = len(radius)
    if n_faces not in (22, 25, 27) or any(v.shape != (len(times), n_faces) for v in data.values()):
        raise RuntimeError(f"Expected graded 22/25/27-face wafer D1 data: {len(times)} / {n_faces}")
    # Accept the original 0–2 us diagnostic and the explicit canonical 0–100 us experiment.
    supported = ((291, 2e-6), (461, 1e-4))
    if not any(len(times) == n and abs(times[-1]-end) < 1e-12 for n,end in supported):
        raise RuntimeError(f"Unexpected D1 timegrid length/end: {len(times)} / {times[-1]}")
    if not (abs(times[0]) < 1e-14 and np.all(np.diff(times) > 0)):
        raise RuntimeError("Incorrect/unsorted native time grid")
    if len(times) == 461:
        # Protect against an incorrect 100 us time grid with matching endpoints.
        expected_ns = list(range(0,101)) + list(range(110,2001,10)) + \
                      list(range(2100,10001,100)) + list(range(11000,100001,1000))
        if len(expected_ns) != len(times) or np.max(np.abs(times-np.array(expected_ns)*1e-9)) > 1e-14:
            raise RuntimeError("100 us run does not match the original 460-step time grid")
    if not all(np.all(np.isfinite(v)) for v in data.values()):
        raise RuntimeError("Nonfinite solver-native face diagnostic")
    # Physical surface area of the annular face in axisymmetric RZ geometry.
    area = np.pi * (rmax[pos]**2 - rmin[pos]**2)
    if np.any(area <= 0):
        raise RuntimeError("Nonpositive annular face area")
    return times, radius[pos], area, data


def first_sign_flip(times, v):
    count = np.sum(v[:, 1:] * v[:, :-1] < 0, axis=1)
    # Exclude initialization row: it is not a validated transient state.
    onset = np.flatnonzero(count[1:] > 0)
    first_any = float(times[onset[0]+1]*1e6) if len(onset) else None
    full = np.flatnonzero(count[1:] == v.shape[1]-1)
    first_all = float(times[full[0]+1]*1e6) if len(full) else None
    return first_any, first_all, count


def audit(times, radius, area, d):
    sigma = d["sigma_wafer"]
    j = d["wafer_net_current_probe"]
    gam = [d[k] for k in ("d1_gamma_o2_positive", "d1_gamma_o_positive",
                          "d1_gamma_o_negative", "d1_gamma_electron")]
    reconstructed_j = E * (gam[0] + gam[1] - gam[2] - gam[3])
    dt = np.diff(times)
    dsigma_dt = np.diff(sigma, axis=0) / dt[:, None]
    j_error = j - reconstructed_j
    balance = dsigma_dt - j[1:]
    scale = max(float(np.sqrt(np.mean(j[1:]**2))), 1e-12)
    current_identity_rel_rms = float(np.sqrt(np.mean(j_error[1:]**2))/scale)
    balance_rel_rms = float(np.sqrt(np.mean(balance**2))/scale)
    # RZ integral of current and accumulated charge; native area-weighted proof.
    total_i = (j * area[None, :]).sum(axis=1)
    total_q = (sigma * area[None, :]).sum(axis=1)
    total_balance = np.diff(total_q)/dt - total_i[1:]
    total_rel_rms = float(np.sqrt(np.mean(total_balance**2)) /
                          max(float(np.sqrt(np.mean(total_i[1:]**2))), 1e-20))
    ne, en, vbar = d["d1_ne_m3"], d["d1_mean_energy_eV"], d["d1_electron_mean_speed_m_s"]
    drop, gamma_e = d["d1_sheath_drop_V"], gam[3]
    if np.any(ne[1:] <= 0) or np.any(en[1:] <= 0) or np.any(vbar[1:] <= 0):
        raise RuntimeError("Nonpositive physical electron state in transient samples")
    Te = (2.0/3.0)*en
    # Production adjacent-sheath law: sticking = 1 and primary thermal wall flux.
    gamma_e_expected = ne*vbar/4*np.exp(-drop/Te)
    electron_scale = max(float(np.sqrt(np.mean(gamma_e[1:]**2))), 1.)
    electron_rel_rms = float(np.sqrt(np.mean((gamma_e_expected[1:]-gamma_e[1:])**2))/electron_scale)
    en_dot_d = d["d1_e_n_V_m"]*d["d1_d_perp_m"]
    snapshots = {}
    for t_us in (0.01, 0.02, 0.1, 0.25, 0.5, 1.0, 2.0,
                 5.0, 10.0, 11.0, 20.0, 24.0, 40.0, 60.0, 100.0):
        if t_us * 1e-6 > times[-1] + 1e-13:
            continue
        k = int(np.argmin(abs(times-t_us*1e-6)))
        snapshots[f"{times[k]*1e6:.5f}us"] = {
            "j_sign_flips": int(np.sum(j[k, 1:]*j[k, :-1] < 0)),
            "sigma_sign_flips": int(np.sum(sigma[k, 1:]*sigma[k, :-1] < 0)),
            "electron_flux_sign_flips": int(np.sum(gamma_e[k, 1:]*gamma_e[k, :-1] < 0)),
            "j_min_A_m2": float(j[k].min()), "j_max_A_m2": float(j[k].max()),
            "sigma_min_C_m2": float(sigma[k].min()), "sigma_max_C_m2": float(sigma[k].max()),
            "en_min_V_m": float(d["d1_e_n_V_m"][k].min()),
            "en_max_V_m": float(d["d1_e_n_V_m"][k].max()),
            "sheath_drop_min_V": float(drop[k].min()),
            "sheath_drop_max_V": float(drop[k].max()),
        }
    first = {}
    for name in ("wafer_net_current_probe", "sigma_wafer", "d1_e_n_V_m",
                 "d1_sheath_drop_V", "d1_gamma_o2_positive", "d1_gamma_o_positive",
                 "d1_gamma_o_negative", "d1_gamma_electron"):
        first_any, first_all, flips = first_sign_flip(times, d[name])
        first[name] = {"first_any_flips_us": first_any,
                       "first_35_flips_us": first_all,
                       "max_sign_flips_after_initial": int(flips[1:].max())}
    normal_err = max(float(np.max(np.abs(d["d1_normal_r"]))),
                     float(np.max(np.abs(d["d1_normal_z"]+1))))
    # No physical mode conclusion: numerical current/sigma identities only.
    integrity = (current_identity_rel_rms < 2e-4 and balance_rel_rms < 2e-4
                 and total_rel_rms < 2e-4 and electron_rel_rms < 2e-4
                 and normal_err < 1e-8 and np.all(d["d1_d_perp_m"] > 0)
                 and np.all(drop >= -1e-8)
                 and np.all(np.abs(d["d1_owner"]) > 0.99))
    return {
        "status": "D1_NATIVE_DIAGNOSTIC_INTEGRITY_PASS" if integrity else "D1_NATIVE_DIAGNOSTIC_INTEGRITY_FAIL",
        "D1_root_cause": "UNKNOWN_PENDING_CAUSAL_DISCRIMINATORS",
        "native_points": len(times), "wafer_faces": len(radius),
        "final_time_us": float(times[-1]*1e6),
        "current_species_sum_rel_rms": current_identity_rel_rms,
        "surface_charge_balance_rel_rms": balance_rel_rms,
        "total_RZ_charge_balance_rel_rms": total_rel_rms,
        "electron_sheath_law_rel_rms": electron_rel_rms,
        "plasma_outward_normal_max_err": normal_err,
        "native_En_times_dperp_range_V": [float(en_dot_d[1:].min()), float(en_dot_d[1:].max())],
        "onset": first, "snapshots": snapshots,
    }


def self_test():
    t = np.array([0, 1e-7, 2e-7])
    n = 36
    radius = np.linspace(0.001, 0.13, n)
    area = np.full(n, 1e-4)
    ne = np.full((3, n), 1e15)
    energy = np.full((3, n), 6.0)
    speed = np.full((3, n), 1e6)
    drop = np.full((3, n), 1.0)
    ge = ne*speed/4*np.exp(-drop/4)
    ga = np.full((3,n), 1e19)
    current = E*(ga-ge)
    sigma = t[:,None] * current
    d = {k: np.zeros((3,n)) for k in FIELDS}
    d.update({
        "sigma_wafer": sigma, "wafer_net_current_probe": current,
        "d1_gamma_o2_positive": ga, "d1_gamma_o_positive": np.zeros((3,n)),
        "d1_gamma_o_negative": np.zeros((3,n)), "d1_gamma_electron": ge,
        "d1_sheath_drop_V": drop, "d1_ne_m3": ne, "d1_mean_energy_eV": energy,
        "d1_electron_mean_speed_m_s": speed, "d1_normal_z": -np.ones((3,n)),
        "d1_d_perp_m": np.full((3,n),1e-3), "d1_owner": np.ones((3,n)),
    })
    assert audit(t,radius,area,d)["status"] == "D1_NATIVE_DIAGNOSTIC_INTEGRITY_PASS"
    d["d1_gamma_o2_positive"] = ga*1.25
    assert audit(t,radius,area,d)["status"] == "D1_NATIVE_DIAGNOSTIC_INTEGRITY_FAIL"
    print("ISSUE397_D1_ANALYZER_SELFTEST_PASS")


def run(path, out):
    times, radius, area, d = load_native_exodus(path)
    out.mkdir(parents=True, exist_ok=True)
    result = audit(times, radius, area, d)
    (out/"d1_native_summary.json").write_text(json.dumps(result,indent=2)+"\n")
    with (out/"d1_native_timeseries.csv").open("w",newline="") as f:
        w = csv.writer(f)
        w.writerow(("time_us", "radius_mm", "area_m2", *FIELDS))
        for k, t in enumerate(times):
            for j, r in enumerate(radius):
                w.writerow((f"{t*1e6:.12g}", f"{r*1000:.12g}",f"{area[j]:.12g}",
                            *(f"{d[x][k,j]:.12g}" for x in FIELDS)))
    print(result["status"])
    print(json.dumps(result,indent=2))
    if result["status"] != "D1_NATIVE_DIAGNOSTIC_INTEGRITY_PASS":
        raise SystemExit("D1 diagnostic integrity failure; not physics FAIL")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",type=Path)
    ap.add_argument("--output",type=Path)
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        self_test()
    else:
        if not args.input or not args.output:
            ap.error("--input and --output required")
        run(args.input,args.output)


if __name__=="__main__":
    main()
