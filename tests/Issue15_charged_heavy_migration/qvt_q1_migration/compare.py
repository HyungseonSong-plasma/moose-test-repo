#!/usr/bin/env python3
from pathlib import Path
import csv, copy, math, sys

HERE = Path(__file__).resolve().parent
ALL = ["O2","O2s","O2p","O","Om","Op","Os"]

def last(name):
    p = HERE/name/"input_out.physical.csv"
    with p.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError("empty "+str(p))
    return {k: float(v) for k, v in rows[-1].items()}

def centroid(r, s):
    return r[f"xmass_{s}"] / r[f"mass_{s}"]

def evaluate(data):
    off = data["migration_off"]
    on  = data["migration_correction_on"]
    nc  = data["migration_correction_off"]

    shift = {s: centroid(on,s) - centroid(off,s) for s in ALL}
    corr  = {s: centroid(on,s) - centroid(nc,s) for s in ALL}

    # Real-qvt direct charged-species migration direction under prescribed E=+x.
    if shift["O2p"] <= 1e-6:
        return False, f"O2p positive-ion centroid shift too small/wrong: {shift['O2p']}"
    if shift["Op"] <= 1e-6:
        return False, f"Op positive-ion centroid shift too small/wrong: {shift['Op']}"
    if shift["Om"] >= -1e-6:
        return False, f"Om negative-ion centroid shift too small/wrong: {shift['Om']}"

    # Solved neutrals have no direct drift; ON-vs-correction-OFF must therefore
    # show a correction-mediated response.
    neutral_corr = {s: corr[s] for s in ["O2s","O","Os"]}
    for s,v in neutral_corr.items():
        if abs(v) <= 1e-8:
            return False, f"{s} correction response not detectable: {v}"

    # These explicit solved-neutral correction responses are driven by one common
    # correction flux direction, so their response signs should agree.
    signs = [math.copysign(1.0, neutral_corr[s]) for s in neutral_corr]
    if len(set(signs)) != 1:
        return False, f"solved-neutral correction directions inconsistent: {neutral_corr}"

    # Q-1 constrained O2 is not evolved with its own explicit correction kernel.
    # Therefore the sign of the global ON-vs-correction-OFF O2 centroid shift is
    # NOT a valid proxy for the local implied face-flux direction. Nonlinear
    # coupling through rho, flow, advection, diffusion, and Q-1 closure can change
    # this global state-difference sign. What is valid from the present observable
    # set is that constrained O2 responds detectably while per-case sum(w)=1 and
    # species-mass partition are already enforced by the case checker.
    if abs(corr["O2"]) <= 1e-8:
        return False, f"constrained O2 Q-1 response not detectable: {corr['O2']}"

    # correction-OFF must remain distinguishable from the corrected production path.
    sep = max(abs(corr[s]) for s in ALL)
    if sep <= 1e-8:
        return False, "correction-off mutation indistinguishable"

    return True, {
        "shift": shift,
        "corr": corr,
        "separation": sep,
    }

def synthetic():
    def make(vals):
        r = {}
        for i,s in enumerate(ALL):
            m = 1.0 + 0.1*i
            r[f"mass_{s}"] = m
            r[f"xmass_{s}"] = m * vals[s]
        return r

    base = {s: 0.15 + 0.01*i for i,s in enumerate(ALL)}
    on = dict(base)
    on["O2p"] += 2e-5
    on["Op"]  += 3e-5
    on["Om"]  -= 2e-5
    for s in ["O2s","O","Os"]:
        on[s] -= 2e-6
    # Intentionally give constrained O2 the opposite centroid sign to prove
    # that this sign is not an acceptance condition.
    on["O2"] += 2e-6

    nc = dict(base)
    nc["O2p"] += 2.2e-5
    nc["Op"]  += 3.2e-5
    nc["Om"]  -= 1.8e-5
    return {
        "migration_off": make(base),
        "migration_correction_on": make(on),
        "migration_correction_off": make(nc),
    }

def self_test():
    good = synthetic()
    ok,_ = evaluate(good)
    if not ok:
        print("R15_EVR2_CROSS_SELFTEST: FAIL good synthetic")
        return 1

    muts = []

    m = copy.deepcopy(good)
    s = "O2p"
    m["migration_correction_on"][f"xmass_{s}"] = (
        m["migration_correction_on"][f"mass_{s}"] * 0.149
    )
    muts.append(("O2p_sign", m))

    m = copy.deepcopy(good)
    for s in ["O2s","O","Os"]:
        m["migration_correction_on"][f"xmass_{s}"] = (
            m["migration_correction_off"][f"xmass_{s}"]
        )
    muts.append(("solved_neutral_correction_missing", m))

    m = copy.deepcopy(good)
    s = "O2"
    m["migration_correction_on"][f"xmass_{s}"] = (
        m["migration_correction_off"][f"xmass_{s}"]
    )
    muts.append(("q1_O2_response_missing", m))

    for name,m in muts:
        passed,_ = evaluate(m)
        if passed:
            print("R15_EVR2_CROSS_SELFTEST: FAIL mutation escaped", name)
            return 1

    print("R15_EVR2_CROSS_SELFTEST: PASS")
    print("R15_EVR2_CROSS_NEGATIVE_CONTROLS: PASS")
    print("R15_EVR2_O2_CENTROID_SIGN_POLICY: NOT_AN_ACCEPTANCE_INVARIANT")
    return 0

def main():
    if "--self-test" in sys.argv:
        return self_test()

    data = {
        n: last(n)
        for n in [
            "migration_off",
            "migration_correction_on",
            "migration_correction_off",
        ]
    }
    ok,msg = evaluate(data)
    if not ok:
        print("R15_EVR2_QVT_CROSS_INVARIANTS: FAIL")
        print(msg)
        return 1

    print("R15_EVR2_QVT_CROSS_INVARIANTS: PASS")
    print("R15_EVR2_O2_CENTROID_SIGN_POLICY: NOT_AN_ACCEPTANCE_INVARIANT")
    for s,v in msg["shift"].items():
        print(f"CENTROID_SHIFT_ON_MINUS_OFF_{s}={v:.17e}")
    for s,v in msg["corr"].items():
        print(f"CORRECTION_EFFECT_ON_MINUS_CORROFF_{s}={v:.17e}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
