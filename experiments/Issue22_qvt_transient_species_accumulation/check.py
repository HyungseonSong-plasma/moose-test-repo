#!/usr/bin/env python3
from pathlib import Path
import csv, json, math, sys

SOLVED = ["O2s","O2p","O","Om","Op","Os"]
ALL = ["O2","O2s","O2p","O","Om","Op","Os"]

def relerr(a,b,scale=1e-300):
    return abs(a-b)/max(abs(a),abs(b),scale)

def f(row,name):
    if name not in row:
        raise ValueError(f"missing CSV column {name}")
    x=float(row[name])
    if not math.isfinite(x):
        raise ValueError(f"non-finite {name}={row[name]!r}")
    return x

def balance_errors(rows, exp):
    solved_max={s:0.0 for s in SOLVED}
    total_max=0.0
    o2_max=0.0
    species_in=exp["expected_species_mdot_kg_per_s"]
    total_in=exp["expected_total_mdot_kg_per_s"]

    for prev,cur in zip(rows[:-1], rows[1:]):
        t0=f(prev,"time"); t1=f(cur,"time")
        dt=t1-t0
        if dt <= 0:
            raise ValueError(f"non-positive physical dt {dt}")

        for s in SOLVED:
            acc=(f(cur,f"mass_{s}")-f(prev,f"mass_{s}"))/dt
            rhs=species_in[s]-f(cur,f"outlet_mdot_{s}")
            e=abs(acc-rhs)/max(abs(species_in[s]),abs(acc),abs(rhs),1e-30)
            solved_max[s]=max(solved_max[s],e)

        acc_total=(f(cur,"mass_total")-f(prev,"mass_total"))/dt
        rhs_total=total_in-f(cur,"outlet_mass_actual")
        et=abs(acc_total-rhs_total)/max(abs(total_in),abs(acc_total),abs(rhs_total),1e-30)
        total_max=max(total_max,et)

        acc_o2=(f(cur,"mass_O2")-f(prev,"mass_O2"))/dt
        rhs_o2=species_in["O2"]-f(cur,"outlet_mdot_O2")
        eo2=abs(acc_o2-rhs_o2)/max(abs(species_in["O2"]),abs(acc_o2),abs(rhs_o2),1e-30)
        o2_max=max(o2_max,eo2)

    return solved_max,total_max,o2_max

def evaluate(rows,exp):
    if len(rows) < 2:
        return False,"need at least 2 physical TIMESTEP_END rows"

    # Runner-owned temporal semantics: t=0 must already be absent here.
    if any(f(r,"time") <= exp["dt_s"]*1e-6 for r in rows):
        return False,"physical CSV still contains initialization-stage row"

    # Static/flow invariants at every physical time.
    max_partition=0.0
    max_closure=0.0
    mn_range_max=0.0
    drho_activity=0.0
    dmn_activity=0.0
    for r in rows:
        if relerr(f(r,"inlet_area"),exp["analytic_inlet_area_m2"]) > 1e-6:
            return False,"inlet area changed"
        if relerr(f(r,"inlet_mdot"),exp["expected_total_mdot_kg_per_s"]) > 2e-8:
            return False,"inlet total mdot changed"
        if relerr(f(r,"outlet_p_avg"),exp["outlet_pressure_Pa"]) > exp["pressure_rel_tol"]:
            return False,f"outlet pressure mismatch at t={f(r,'time')}"

        sw=max(abs(f(r,"sum_w_min")-1.0),abs(f(r,"sum_w_max")-1.0))
        max_closure=max(max_closure,sw)

        species_mass_sum=0.0
        for s in ALL:
            mn=f(r,f"w_{s}_min"); mx=f(r,f"w_{s}_max")
            if mn < -1e-10 or mx > 1.0+1e-10:
                return False,f"{s} out of bounds at t={f(r,'time')}: {mn},{mx}"
            D=f(r,f"Dmix_{s}_avg")
            if D <= 0:
                return False,f"{s} D_mix not positive at t={f(r,'time')}"
            species_mass_sum += f(r,f"mass_{s}")

        part=relerr(species_mass_sum,f(r,"mass_total"),1e-30)
        max_partition=max(max_partition,part)
        mn_range_max=max(mn_range_max,f(r,"Mn_max")-f(r,"Mn_min"))
        drho_activity=max(drho_activity,abs(f(r,"drho_dt_avg")))
        dmn_activity=max(dmn_activity,abs(f(r,"dMn_dt_avg")))

    if max_closure > exp["sum_w_abs_tol"]:
        return False,f"sum(w) closure max error {max_closure}"
    if max_partition > exp["mass_partition_rel_tol"]:
        return False,f"sum species inventory != total inventory: rel={max_partition}"
    if mn_range_max < exp["min_Mn_spatial_range"]:
        return False,f"composition-dependent Mn not activated: max spatial range={mn_range_max}"
    if max(drho_activity,dmn_activity) < exp["min_transient_activity"]:
        return False,f"transient Mn/rho derivative activity too small: dMn={dmn_activity}, drho={drho_activity}"

    solved,total,o2=balance_errors(rows,exp)
    for s,e in solved.items():
        if e > exp["inventory_balance_rel_tol_solved"]:
            return False,f"{s} conservative inventory balance failed: max_rel={e}"
    if total > exp["inventory_balance_rel_tol_total"]:
        return False,f"mixture inventory balance failed: max_rel={total}"
    if o2 > exp["inventory_balance_rel_tol_constrained_O2"]:
        return False,f"constrained O2 implied inventory balance failed: max_rel={o2}"

    return True,{
        "solved_balance_max":solved,
        "total_balance_max":total,
        "O2_balance_max":o2,
        "mass_partition_max":max_partition,
        "closure_max":max_closure,
        "Mn_spatial_range_max":mn_range_max,
        "drho_activity":drho_activity,
        "dMn_activity":dmn_activity,
    }

def synthetic_rows(exp):
    # Algebraic self-test data. Inventories are generated recursively from
    # BE balance: M_n = M_{n-1} + dt*(mdot_in - mdot_out_n).
    dt=exp["dt_s"]
    rows=[]
    masses={"total":1.0e-6}
    for s in ALL:
        masses[s]=exp["inlet_mass_fractions"][s]*masses["total"]

    for n in range(1,5):
        t=n*dt
        # choose transient outlet flow below inlet so inventory grows
        out_total=0.8*exp["expected_total_mdot_kg_per_s"]
        out={s:0.8*exp["expected_species_mdot_kg_per_s"][s] for s in ALL}
        if n>1:
            masses["total"] += dt*(exp["expected_total_mdot_kg_per_s"]-out_total)
            for s in ALL:
                masses[s] += dt*(exp["expected_species_mdot_kg_per_s"][s]-out[s])
        r={
          "time":str(t),
          "inlet_area":str(exp["analytic_inlet_area_m2"]),
          "inlet_mdot":str(exp["expected_total_mdot_kg_per_s"]),
          "outlet_mass_actual":str(out_total),
          "outlet_p_avg":str(exp["outlet_pressure_Pa"]),
          "sum_w_min":"1","sum_w_max":"1",
          "Mn_min":"0.0254","Mn_max":"0.0258",
          "drho_dt_avg":"1e-7","dMn_dt_avg":"1e-5",
          "mass_total":str(masses["total"]),
        }
        for s in ALL:
            y=exp["inlet_mass_fractions"][s]
            r[f"w_{s}_avg"]=str(y)
            r[f"w_{s}_min"]=str(max(0.0,y-1e-3))
            r[f"w_{s}_max"]=str(min(1.0,y+1e-3))
            r[f"Dmix_{s}_avg"]="1e-3"
            r[f"outlet_mdot_{s}"]=str(out[s])
            r[f"mass_{s}"]=str(masses[s])
        rows.append(r)
    return rows

def self_test(exp):
    rows=synthetic_rows(exp)
    ok,msg=evaluate(rows,exp)
    if not ok:
        raise SystemExit("R22_EVR2_CHECKER_SELFTEST: FAIL good synthetic: "+str(msg))

    mutations=[
      ("inventory",lambda rs: rs[-1].__setitem__("mass_O",str(float(rs[-1]["mass_O"])+1e-9))),
      ("closure",lambda rs: rs[-1].__setitem__("sum_w_max","0.99")),
      ("partition",lambda rs: rs[-1].__setitem__("mass_O2",str(float(rs[-1]["mass_O2"])+1e-7))),
      ("bounds",lambda rs: rs[-1].__setitem__("w_Om_min","-0.1")),
      ("dmix",lambda rs: rs[-1].__setitem__("Dmix_Op_avg","0")),
      ("mn_inactive",lambda rs: [r.update({"Mn_min":"0.0258","Mn_max":"0.0258"}) for r in rs]),
    ]
    import copy
    for name,mut in mutations:
        rs=copy.deepcopy(rows); mut(rs)
        passed,_=evaluate(rs,exp)
        if passed:
            raise SystemExit("R22_EVR2_CHECKER_SELFTEST: FAIL mutation escaped "+name)
    print("R22_EVR2_CHECKER_SELFTEST: PASS")
    print("R22_EVR2_CHECKER_NEGATIVE_CONTROLS: PASS")

def main():
    if len(sys.argv)==3 and sys.argv[1]=="--self-test":
        exp=json.loads(Path(sys.argv[2]).read_text())
        return self_test(exp)
    if len(sys.argv)!=3:
        raise SystemExit("usage: check.py input_out.physical.csv expected.json | --self-test expected.json")
    cp=Path(sys.argv[1]); ep=Path(sys.argv[2])
    if not cp.is_file(): raise SystemExit("missing physical CSV "+str(cp))
    exp=json.loads(ep.read_text())
    with cp.open() as fh:
        rows=list(csv.DictReader(fh))
    ok,msg=evaluate(rows,exp)
    if not ok:
        raise SystemExit("FAIL "+str(msg))
    print("R22_QVT_TRANSIENT_INVENTORY_CHECK: PASS")
    print("SOLVED_BALANCE_MAX_REL="+json.dumps(msg["solved_balance_max"],sort_keys=True))
    print(f"TOTAL_BALANCE_MAX_REL={msg['total_balance_max']:.9e}")
    print(f"O2_BALANCE_MAX_REL={msg['O2_balance_max']:.9e}")
    print(f"MASS_PARTITION_MAX_REL={msg['mass_partition_max']:.9e}")
    print(f"SUM_W_MAX_ABS_ERROR={msg['closure_max']:.9e}")
    print(f"MN_SPATIAL_RANGE_MAX={msg['Mn_spatial_range_max']:.9e}")
    print(f"MAX_ABS_DRHO_DT_AVG={msg['drho_activity']:.9e}")
    print(f"MAX_ABS_DMN_DT_AVG={msg['dMn_activity']:.9e}")

if __name__=="__main__":
    main()
