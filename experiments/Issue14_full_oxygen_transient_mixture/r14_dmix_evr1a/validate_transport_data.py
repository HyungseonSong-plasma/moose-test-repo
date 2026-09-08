#!/usr/bin/env python3
from __future__ import annotations
import json, math, sys
from pathlib import Path

PI = 3.14159265358979323846
TWOPI = 2.0*PI
KB = 1.3806503e-23
MU0 = PI*4.0e-7
C0 = 299792458.0
EPS0 = 1.0/(MU0*C0*C0)
QE = 1.602176565e-19
NA = 6.0221415e23
SFAC_11 = 0.66467
LFAC_1 = 1.1046
FAC = PI*LFAC_1*SFAC_11*math.sqrt(QE*QE/(TWOPI*EPS0*KB))

ACTIVE = ["O2","O2s","O2p","O","Om","Op","Os"]
EXPECTED_SPECIES = {
    "O2":  (0.032,"O2"),
    "O2s": (0.032,"O2"),
    "O2p": (0.032,"O2+"),
    "O":   (0.016,"O"),
    "Om":  (0.016,"O-"),
    "Op":  (0.016,"O+"),
    "Os":  (0.016,"O"),
}
CHARGE = {"O2":0,"O":0,"O2+":1,"O+":1,"O-":-1}

EXPECTED_STATIC = {
    tuple(sorted(("O","O"))),
    tuple(sorted(("O","O2"))),
    tuple(sorted(("O2","O2"))),
    tuple(sorted(("O","O+"))),
    tuple(sorted(("O","O2+"))),
    tuple(sorted(("O+","O2"))),
    tuple(sorted(("O2","O2+"))),
    tuple(sorted(("O","O-"))),
    tuple(sorted(("O-","O2"))),
}
EXPECTED_DYNAMIC = {
    tuple(sorted(("O2+","O2+"))),
    tuple(sorted(("O2+","O-"))),
    tuple(sorted(("O2+","O+"))),
    tuple(sorted(("O-","O-"))),
    tuple(sorted(("O-","O+"))),
    tuple(sorted(("O+","O+"))),
}

def key(a,b): return tuple(sorted((a,b)))

def parse(path):
    species={}
    pairs={}
    cur=None
    for n,raw in enumerate(path.read_text().splitlines(),1):
        line=raw.split("#",1)[0].strip()
        if not line: continue
        f=line.split()
        if cur is None:
            if f[0]=="species":
                if len(f)!=4: raise ValueError(f"line {n}: malformed species")
                species[f[1]]=(float(f[2]),f[3])
            elif f[0]=="pair":
                if len(f)!=5: raise ValueError(f"line {n}: malformed pair")
                cur={"a":f[1],"b":f[2],"B":float(f[3]),"C":float(f[4]),"rows":[]}
            else:
                raise ValueError(f"line {n}: unknown keyword {f[0]}")
        else:
            if f[0]=="endpair":
                k=key(cur["a"],cur["b"])
                if k in pairs: raise ValueError(f"duplicate pair {k}")
                pairs[k]=cur
                cur=None
            else:
                if len(f)!=3: raise ValueError(f"line {n}: malformed row")
                cur["rows"].append(tuple(map(float,f)))
    if cur is not None: raise ValueError("unterminated pair")
    return species,pairs

def q_langevin_unmultiplied(alpha_A3,T):
    q_si = FAC*math.sqrt(alpha_A3*1e-30/T)
    return q_si/(PI*1e-20)

def rel(a,b):
    return abs(a-b)/max(abs(b),1e-300)

def main(path):
    failures=[]
    species,pairs=parse(path)

    if species != EXPECTED_SPECIES:
        failures.append(f"species/alias/mass contract mismatch: {species}")

    if set(pairs) != EXPECTED_STATIC:
        failures.append(f"static pair set mismatch missing={EXPECTED_STATIC-set(pairs)} extra={set(pairs)-EXPECTED_STATIC}")

    aliases=[EXPECTED_SPECIES[s][1] for s in ACTIVE]
    resolved_static=set()
    resolved_dynamic=set()
    for i,a in enumerate(aliases):
        for b in aliases[i:]:
            k=key(a,b)
            if CHARGE.get(a,0)!=0 and CHARGE.get(b,0)!=0:
                resolved_dynamic.add(k)
            else:
                resolved_static.add(k)
                if k not in pairs:
                    failures.append(f"missing required static resolver pair: {a}|{b}")

    if resolved_static != EXPECTED_STATIC:
        failures.append("seven-species static resolver set differs from canonical expectation")
    if resolved_dynamic != EXPECTED_DYNAMIC:
        failures.append("seven-species dynamic charged pair set differs from canonical expectation")

    # Every table contract.
    for k,p in pairs.items():
        rows=p["rows"]
        if len(rows)<2: failures.append(f"{k}: fewer than 2 rows"); continue
        Ts=[r[0] for r in rows]
        if any(not (Ts[i]>Ts[i-1]) for i in range(1,len(Ts))):
            failures.append(f"{k}: non-increasing temperature grid")
        if any(any(not math.isfinite(v) or v<=0 for v in r) for r in rows):
            failures.append(f"{k}: non-positive/non-finite row")

    # B*,C* classes.
    neutral={key("O","O"),key("O","O2"),key("O2","O2")}
    for k in neutral:
        p=pairs[k]
        if abs(p["B"]-1.15)>1e-15 or abs(p["C"]-0.92)>1e-15:
            failures.append(f"{k}: neutral B*/C* mismatch")
    for k in EXPECTED_STATIC-neutral:
        p=pairs[k]
        if abs(p["B"]-1.20)>1e-15 or abs(p["C"]-0.85)>1e-15:
            failures.append(f"{k}: ion-neutral B*/C* mismatch")

    # Independent Langevin parity.
    for k,alpha in [(key("O","O-"),0.80),(key("O-","O2"),1.58)]:
        p=pairs[k]
        max_node=0.0
        for T,q11,q22 in p["rows"]:
            ref=q_langevin_unmultiplied(alpha,T)
            max_node=max(max_node,rel(q11,ref))
            if rel(q22,1.1*q11)>5e-14:
                failures.append(f"{k}: Q22 != 1.1 Q11 at T={T}")
        print(f"{k}: Langevin max_node_rel={max_node:.3e}")
        if max_node>5e-13:
            failures.append(f"{k}: Langevin Q11 node parity > 5e-13")

        # Linear interpolation error against analytic 1/sqrt(T) at interval midpoints.
        rows=p["rows"]
        max_mid=0.0
        for r0,r1 in zip(rows[:-1],rows[1:]):
            T0,q0,_=r0; T1,q1,_=r1
            Tm=0.5*(T0+T1)
            qlin=q0+(q1-q0)*(Tm-T0)/(T1-T0)
            qref=q_langevin_unmultiplied(alpha,Tm)
            max_mid=max(max_mid,rel(qlin,qref))
        print(f"{k}: Langevin max_midpoint_interp_rel={max_mid:.12e}")
        if max_mid>0.01:
            failures.append(f"{k}: Langevin linear interpolation error > 1%")

    # Historical independent O-/O2 reduced mobility signature at 300 K.
    q11_tab = pairs[key("O-","O2")]["rows"][0][1]
    q11_si = q11_tab*PI*1e-20
    mi=0.016/NA
    mj=0.032/NA
    T=300.0
    nD=math.sqrt(T)*(3.0/16.0)*math.sqrt(2.0*PI*KB*(mi+mj)/(mi*mj))/q11_si
    N0=101325.0/(KB*273.15)
    K0=QE*nD/(KB*T*N0)
    K0_cm2=K0*1e4
    print(f"Ominus_O2_K0_300K={K0_cm2:.12f} cm^2/(V s)")
    if abs(K0_cm2-3.381390851205)>5e-12:
        failures.append("O-/O2 300 K reduced-mobility signature mismatch")

    print(f"STATIC_PAIR_COUNT={len(pairs)}")
    print(f"DYNAMIC_PAIR_COUNT={len(EXPECTED_DYNAMIC)}")
    if failures:
        print("R14_7SPECIES_TRANSPORT_DATA: FAIL")
        for x in failures: print("  -",x)
        return 1
    print("R14_7SPECIES_TRANSPORT_DATA: PASS")
    return 0

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("usage: validate_transport_data.py <transport_data.txt>")
    raise SystemExit(main(Path(sys.argv[1])))
