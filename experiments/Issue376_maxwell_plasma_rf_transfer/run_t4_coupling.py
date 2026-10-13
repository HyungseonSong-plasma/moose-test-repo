#!/usr/bin/env python3
"""Issue #376 T4 reduced segregated Maxwell/plasma coupling discriminator."""
from __future__ import annotations
import argparse, csv, json, math, shlex, subprocess, sys
from pathlib import Path

NE = 1.0e15
E0 = 4.0
P = 1.333223684
TG = 300.0
FREQ = 13.56e6
NA = 6.02214076e23
QE = 1.602176634e-19
ME = 9.1093837015e-31
KB = 1.380649e-23
TEND = 2.0e-6
LEVELS = (("coarse", 1.25e-7), ("medium", 6.25e-8), ("fine", 3.125e-8))
PICARD_TOL = 1.0e-7
PICARD_MAX = 12
CONTRACTION_MAX = 0.8
POWER_TOL = 1.0e-10
RAW_TOL = 2.0e-2
REFINE_RATIO_MAX = 0.8
FINE_MEDIUM_TOL = 5.0e-3
VOL_TOL = 1.0e-10


def args():
    p = argparse.ArgumentParser()
    for name in ("physics", "maxwell", "target", "table", "output_dir", "analysis"):
        p.add_argument("--" + name.replace("_", "-"), dest=name, required=True)
    return p.parse_args()


def rows(path):
    with Path(path).open(newline="") as f:
        return list(csv.DictReader(f))


def run(cmd, log):
    log = Path(log); log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as f:
        f.write("$ " + " ".join(shlex.quote(x) for x in cmd) + "\n"); f.flush()
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, text=True)
    if r.returncode:
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-80:])
        raise RuntimeError(f"command failed ({r.returncode}): {' '.join(cmd)}\n{tail}")


def rel(a, b):
    return abs(a - b) / max(abs(b), 1.0e-300)


def table(path):
    x, y = [], []
    for line in Path(path).read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"): continue
        c = s.split()
        x.append(float(c[0])); y.append(float(c[1]))
    if len(x) < 2 or any(x[i+1] <= x[i] for i in range(len(x)-1)):
        raise RuntimeError("invalid electron mobility table")
    return x, y


def interp(v, x, y):
    if v < x[0] or v > x[-1]:
        raise RuntimeError(f"mean energy {v} eV outside lookup [{x[0]}, {x[-1]}]")
    if v == x[-1]: return y[-1]
    j = 0
    while j + 1 < len(x) and x[j+1] < v: j += 1
    t = (v - x[j]) / (x[j+1] - x[j])
    return y[j] + t * (y[j+1] - y[j])


def sigma(eps, x, muN):
    muN_v = interp(eps, x, muN)
    nn = P / (KB * TG)
    mu = muN_v / nn
    nu = QE / (ME * mu)
    om = 2.0 * math.pi * FREQ
    den = nu * nu + om * om
    sr = NE * QE * QE * nu / (ME * den)
    si = -NE * QE * QE * om / (ME * den)
    if not (math.isfinite(sr) and math.isfinite(si) and sr > 0 and si < 0):
        raise RuntimeError("invalid Drude conductivity")
    return {"mean_energy_eV": eps, "muN": muN_v, "mobility": mu,
            "collision_frequency_Hz": nu, "sigma_real_S_per_m": sr,
            "sigma_imag_S_per_m": si}


def one_level(name, dt, a, x, muN, shared):
    nstep = int(round(TEND / dt))
    if abs(nstep * dt - TEND) > 1e-15: raise RuntimeError("dt does not divide TEND")
    out = Path(a.output_dir) / name; out.mkdir(parents=True, exist_ok=True)
    case = Path(a.target).parent
    ne_mol = NE / NA
    prev = E0
    steps = []
    max_contract = max_power = max_raw = 0.0
    max_iters = 0

    for k in range(1, nstep + 1):
        guess = prev; recs = []; residuals = []; accepted = None
        for it in range(1, PICARD_MAX + 1):
            d = out / f"step_{k:02d}" / f"iter_{it:02d}"; d.mkdir(parents=True, exist_ok=True)
            c = sigma(guess, x, muN); sr = c["sigma_real_S_per_m"]; si = c["sigma_imag_S_per_m"]
            mb = d / "maxwell"
            run([a.physics, "-i", a.maxwell, f"plasma_sigma_real={sr:.17g}",
                 f"plasma_sigma_imag={si:.17g}", f"Outputs/file_base={mb}"], d / "maxwell.log")
            mr = rows(mb.with_suffix(".csv"))[-1]
            pabs = float(mr["P_abs"]); field = math.hypot(float(mr["E_real_l2"]), float(mr["E_imag_l2"]))
            if not (pabs > 0 and field > 0): raise RuntimeError("non-positive Maxwell response")
            me_rel = mb.with_suffix(".e").relative_to(case)
            u0 = ne_mol * prev; logu0 = math.log(u0)
            common = [a.physics, "-i", a.target, f"maxwell_solution_file={me_rel}",
                      f"plasma_sigma_real={sr:.17g}", f"energy_initial_log={logu0:.17g}",
                      f"dt_t4={dt:.17g}"]
            if not shared.get("checked"):
                run([a.physics, "--check-input", "-i", a.target,
                     f"maxwell_solution_file={me_rel}", f"plasma_sigma_real={sr:.17g}",
                     f"energy_initial_log={logu0:.17g}", f"dt_t4={dt:.17g}",
                     "source_enable=0", "rf_scale=1"], Path(a.output_dir) / "check_target.log")
                shared["checked"] = True
            rb = d / "raw"
            run(common + ["source_enable=0", "rf_scale=1", f"Outputs/file_base={rb}"], d / "raw.log")
            rr = rows(rb.with_suffix(".csv")); raw = float(rr[-1]["P_rf_raw_W"])
            if raw <= 0: raise RuntimeError("non-positive raw mapped power")
            scale = pabs / raw; raw_def = rel(raw, pabs)
            vol = float(rr[0]["electron_energy_inventory_eV_mol"]) / u0
            if "volume" not in shared: shared["volume"] = vol
            elif rel(vol, shared["volume"]) > VOL_TOL: raise RuntimeError("plasma volume changed")
            sb = d / "scaled"
            run(common + ["source_enable=1", f"rf_scale={scale:.17g}", f"Outputs/file_base={sb}"], d / "scaled.log")
            srw = rows(sb.with_suffix(".csv"))[-1]
            pscaled = float(srw["P_rf_scaled_W"]); inv = float(srw["electron_energy_inventory_eV_mol"])
            emin = float(srw["electron_energy_min_eV_mol_m3"]); emax = float(srw["electron_energy_max_eV_mol_m3"])
            source = float(srw["S_rf_eV_mol_s"])
            if not (pscaled > 0 and inv > 0 and emin > 0 and emax > 0 and source > 0):
                raise RuntimeError("non-positive T4 energy/source metric")
            cand = inv / (vol * ne_mol); r = rel(cand, guess); pc = rel(pscaled, pabs)
            if cand < x[0] or cand > x[-1]: raise RuntimeError("mean energy left lookup range")
            if raw_def > RAW_TOL: raise RuntimeError(f"raw mapping defect {raw_def} > {RAW_TOL}")
            if pc > POWER_TOL: raise RuntimeError(f"power closure {pc} > {POWER_TOL}")
            residuals.append(r); max_power = max(max_power, pc); max_raw = max(max_raw, raw_def)
            recs.append({"iteration": it, "guess_mean_energy_eV": guess,
                         "candidate_mean_energy_eV": cand, "picard_relative_residual": r,
                         "conductivity": c, "maxwell_field_l2": field, "maxwell_P_abs_W": pabs,
                         "target_P_raw_W": raw, "raw_mapping_relative_defect": raw_def,
                         "rf_scale": scale, "target_P_scaled_W": pscaled,
                         "power_closure_relative": pc, "integrated_source_eV_mol_s": source,
                         "electron_energy_inventory_eV_mol": inv,
                         "electron_energy_min_eV_mol_m3": emin, "electron_energy_max_eV_mol_m3": emax})
            print(f"T4 {name} step={k}/{nstep} iter={it} eps={guess:.9g}->{cand:.9g} "
                  f"res={r:.3e} sigma=({sr:.6g},{si:.6g}) P={pabs:.8g}W scale={scale:.8g}", flush=True)
            accepted = cand
            if r <= PICARD_TOL: break
            guess = cand
        if accepted is None or residuals[-1] > PICARD_TOL:
            raise RuntimeError(f"{name} step {k} did not converge in {PICARD_MAX} Picard iterations")
        ratios = [b/a0 for a0,b in zip(residuals,residuals[1:]) if a0 > 10*PICARD_TOL]
        mc = max(ratios) if ratios else 0.0
        if mc > CONTRACTION_MAX: raise RuntimeError(f"Picard contraction {mc} > {CONTRACTION_MAX}")
        max_contract = max(max_contract, mc); max_iters = max(max_iters, len(recs)); prev = accepted
        steps.append({"step": k, "time_s": k*dt, "accepted_mean_energy_eV": prev,
                      "picard_iterations": len(recs), "picard_residuals": residuals,
                      "max_contraction_ratio": mc, "iterations": recs})
    fc = sigma(prev, x, muN); last = steps[-1]["iterations"][-1]
    return {"name": name, "dt_s": dt, "num_physical_steps": nstep,
            "final_mean_energy_eV": prev, "final_conductivity": fc,
            "final_maxwell_P_abs_W": last["maxwell_P_abs_W"],
            "max_picard_iterations": max_iters, "max_picard_contraction_ratio": max_contract,
            "max_power_closure_relative": max_power, "max_raw_mapping_relative_defect": max_raw,
            "steps": steps}


def history(path, levels):
    keys = ["level","dt_s","step","time_s","iteration","guess_mean_energy_eV",
            "candidate_mean_energy_eV","picard_relative_residual","sigma_real_S_per_m",
            "sigma_imag_S_per_m","maxwell_P_abs_W","target_P_raw_W","rf_scale",
            "target_P_scaled_W","power_closure_relative"]
    with Path(path).open("w", newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys); w.writeheader()
        for L in levels:
            for S in L["steps"]:
                for R in S["iterations"]:
                    C=R["conductivity"]
                    w.writerow({"level":L["name"],"dt_s":L["dt_s"],"step":S["step"],"time_s":S["time_s"],
                                "iteration":R["iteration"],"guess_mean_energy_eV":R["guess_mean_energy_eV"],
                                "candidate_mean_energy_eV":R["candidate_mean_energy_eV"],
                                "picard_relative_residual":R["picard_relative_residual"],
                                "sigma_real_S_per_m":C["sigma_real_S_per_m"],"sigma_imag_S_per_m":C["sigma_imag_S_per_m"],
                                "maxwell_P_abs_W":R["maxwell_P_abs_W"],"target_P_raw_W":R["target_P_raw_W"],
                                "rf_scale":R["rf_scale"],"target_P_scaled_W":R["target_P_scaled_W"],
                                "power_closure_relative":R["power_closure_relative"]})


def main():
    a=args(); out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True); ap=Path(a.analysis)
    result={"gate":"T4 coupling convergence","status":"FAIL",
            "scope":"Reduced T4: fixed n_e=1e15 m^-3, volume-mean electron-energy state, 2-D Maxwell and 2-D RF source; full spatial plasma feedback remains T6.",
            "acceptance":{"total_time_s":TEND,"dt_levels_s":dict(LEVELS),"picard_relative_tolerance":PICARD_TOL,
                          "picard_max_iterations":PICARD_MAX,"picard_contraction_ratio_max":CONTRACTION_MAX,
                          "power_closure_relative_tolerance":POWER_TOL,"raw_mapping_relative_tolerance":RAW_TOL,
                          "timestep_refinement_ratio_max":REFINE_RATIO_MAX,"fine_medium_relative_tolerance":FINE_MEDIUM_TOL},
            "failures":[]}
    try:
        for p in (Path(a.physics),Path(a.maxwell),Path(a.target),Path(a.table)):
            if not p.is_file(): raise RuntimeError(f"missing required input: {p}")
        x,muN=table(a.table); result["lookup_range_eV"]=[x[0],x[-1]]
        result["initial_conductivity"]=sigma(E0,x,muN)
        shared={"checked":False}; levels=[one_level(n,dt,a,x,muN,shared) for n,dt in LEVELS]
        result["levels"]=levels; result["plasma_volume_m3"]=shared["volume"]
        ec,em,ef=[float(L["final_mean_energy_eV"]) for L in levels]
        dcm=abs(em-ec)/abs(ef); dmf=abs(ef-em)/abs(ef)
        ratio=dmf/dcm if dcm>1e-14 else (0.0 if dmf<=1e-14 else math.inf)
        order=math.log(dcm/max(dmf,1e-300),2) if dcm>1e-14 else math.inf
        result["timestep_refinement"]={"coarse_medium_mean_energy_relative_difference":dcm,
            "medium_fine_mean_energy_relative_difference":dmf,
            "difference_ratio_medium_fine_over_coarse_medium":ratio,"observed_order_from_mean_energy":order}
        failures=[]
        if max(L["max_picard_contraction_ratio"] for L in levels)>CONTRACTION_MAX: failures.append("picard_contraction")
        if max(L["max_power_closure_relative"] for L in levels)>POWER_TOL: failures.append("power_closure")
        if max(L["max_raw_mapping_relative_defect"] for L in levels)>RAW_TOL: failures.append("raw_mapping")
        if not all(E>E0 for E in (ec,em,ef)): failures.append("positive_rf_heating_response")
        if dmf>FINE_MEDIUM_TOL: failures.append("fine_medium_timestep_difference")
        if ratio>REFINE_RATIO_MAX: failures.append("timestep_refinement_not_contracting")
        result["failures"]=failures; result["status"]="PASS" if not failures else "FAIL"
        history(out/"history.csv",levels); ap.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        print("T4_COUPLED_CONVERGENCE_"+result["status"])
        print(f"final mean energy [eV]: coarse={ec:.12g} medium={em:.12g} fine={ef:.12g}")
        print(f"refinement: d_cm={dcm:.6e} d_mf={dmf:.6e} ratio={ratio:.6e} order={order:.6g}")
        print(f"failures={failures}")
        return 0 if not failures else 1
    except Exception as e:
        result["failures"]=[f"runtime: {e}"]; result["exception"]=repr(e)
        ap.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        print(f"T4_COUPLED_CONVERGENCE_ERROR: {e}",file=sys.stderr); return 2

if __name__=="__main__": raise SystemExit(main())
