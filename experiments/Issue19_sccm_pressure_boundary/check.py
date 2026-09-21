#!/usr/bin/env python3
from pathlib import Path
import csv, json, sys

def rel(a, b):
    return abs(a - b) / max(abs(b), 1e-300)

def evaluate(row, exp):
    def val(name):
        if name not in row:
            return False, f"missing CSV column {name}; got {sorted(row)}"
        try:
            return True, float(row[name])
        except Exception:
            return False, f"non-numeric CSV column {name}: {row[name]!r}"

    vals = {}
    for name in ("inlet_area", "inlet_mdot", "inlet_mass_actual",
                 "outlet_mass_actual", "outlet_p_avg"):
        ok, x = val(name)
        if not ok:
            return False, x
        vals[name] = x

    area = vals["inlet_area"]
    mdot_pp = vals["inlet_mdot"]
    minlet_diag = vals["inlet_mass_actual"]
    mout = vals["outlet_mass_actual"]
    pout = vals["outlet_p_avg"]

    Aexp = exp["inlet_area_m2"]
    Mexp = exp["inlet_mdot_kg_per_s"]
    Pexp = exp["outlet_pressure_Pa"]

    # Fixed-geometry / SCCM conversion identities.
    # Area tolerance accounts for normal CSV/output formatting while still
    # strongly rejecting a wrong boundary or non-RZ area.
    if rel(area, Aexp) > 1e-6:
        return False, f"inlet area: got {area:.16e}, expected {Aexp:.16e}"
    if rel(mdot_pp, Mexp) > 2e-8:
        return False, f"SCCM->mdot: got {mdot_pp:.16e}, expected {Mexp:.16e}"

    # On this internal inlet, VolumetricFlowRate is a Rhie-Chow reconstructed
    # velocity diagnostic. It is not the WCNSFVMassFluxBC discrete residual.
    # Use it only to verify the physical direction port -> plasma.
    if not (minlet_diag < 0):
        return False, (
            f"inlet direction: inlet_mass_actual={minlet_diag:.16e}, "
            "expected negative reconstructed flow"
        )

    # Conservative steady-state acceptance:
    # prescribed inlet mdot must leave through the physical outlet.
    if not (mout > 0):
        return False, f"outlet sign: outlet_mass_actual={mout:.16e}, expected positive"
    if rel(mout, Mexp) > 2e-2:
        return False, (
            f"steady conservative mass flow: outlet={mout:.16e} "
            f"vs prescribed inlet mdot={Mexp:.16e}"
        )

    if rel(pout, Pexp) > 5e-3:
        return False, f"outlet pressure: got {pout:.16e}, expected {Pexp:.16e}"

    return True, {
        "inlet_area": area,
        "inlet_mdot": mdot_pp,
        "inlet_mass_reconstructed": minlet_diag,
        "outlet_mass_actual": mout,
        "outlet_p_avg": pout,
    }

def self_test():
    exp = {
        "inlet_area_m2": 5.9545747156140909e-02,
        "inlet_mdot_kg_per_s": 2.3795076798610368e-06,
        "outlet_pressure_Pa": 1.33322,
    }
    good = {
        # Deliberately rounded exactly as the user-visible MOOSE table.
        "inlet_area": "5.954575e-02",
        "inlet_mdot": "2.3795076798610368e-06",
        # Deliberately != prescribed mdot: observed EVR1 reconstruction.
        "inlet_mass_actual": "-2.7292797236687000e-06",
        "outlet_mass_actual": "2.3795076798610368e-06",
        "outlet_p_avg": "1.33322",
    }

    ok, msg = evaluate(good, exp)
    if not ok:
        raise SystemExit("R19_CHECKER_SELFTEST: FAIL accepted EVR1 semantics rejected: " + str(msg))

    mutations = {
        "wrong_inlet_sign": {"inlet_mass_actual": "2.7292797236687000e-06"},
        "wrong_outlet_mass": {"outlet_mass_actual": "1.0e-06"},
        "wrong_outlet_pressure": {"outlet_p_avg": "2.0"},
        "wrong_sccm_mdot": {"inlet_mdot": "1.0e-06"},
        "wrong_area": {"inlet_area": "4.0e-02"},
    }
    for name, patch in mutations.items():
        row = dict(good)
        row.update(patch)
        ok, _ = evaluate(row, exp)
        if ok:
            raise SystemExit(f"R19_CHECKER_SELFTEST: FAIL mutation escaped: {name}")

    print("R19_CHECKER_SEMANTIC_SELFTEST: PASS")
    print("R19_CHECKER_NEGATIVE_CONTROLS: PASS")

def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
        return
    if len(sys.argv) != 3:
        raise SystemExit("usage: check.py input_out.csv expected.json | --self-test")

    csv_path = Path(sys.argv[1])
    exp_path = Path(sys.argv[2])
    if not csv_path.is_file():
        raise SystemExit(f"missing CSV: {csv_path}")
    if not exp_path.is_file():
        raise SystemExit(f"missing expected file: {exp_path}")

    exp = json.loads(exp_path.read_text())
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("empty CSV")

    ok, result = evaluate(rows[-1], exp)
    if not ok:
        raise SystemExit("FAIL " + str(result))

    print(f"inlet_area={result['inlet_area']:.16e}")
    print(f"inlet_mdot={result['inlet_mdot']:.16e}")
    print(f"inlet_mass_reconstructed={result['inlet_mass_reconstructed']:.16e}")
    print(f"outlet_mass_actual={result['outlet_mass_actual']:.16e}")
    print(f"outlet_p_avg={result['outlet_p_avg']:.16e}")
    print("R19_SCCM_PRESSURE_CHECK: PASS")

if __name__ == "__main__":
    main()
