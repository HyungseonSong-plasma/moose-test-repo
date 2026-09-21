#!/usr/bin/env python3
from __future__ import annotations
import bisect
import math
import sys
from pathlib import Path

SPECIES_ORDER = ["O2","O2s","O2p","O","Om","Op","Os"]
Y = [0.70,0.05,0.01,0.10,0.01,0.01,0.12]

T_G = 600.0
P = 13.332
T_E = 20000.0
NE_A = 1.0e16
NE_B = 1.0e18

# Independent CODATA constants. The production source's QPX_CONSTANTS are not
# read by this oracle.
PI = math.pi
KB = 1.380649e-23
NA = 6.02214076e23
EPS0 = 8.8541878128e-12
QE = 1.602176634e-19

DEBYE_NE_FLOOR = 1.0e-16
DEBYE_TSTAR = [
    0.1,0.2,0.3,0.4,0.6,0.8,1,2,3,4,6,8,10,20,30,40,60,80,100,
    200,300,400,600,800,1000,10000
]
# Columns: Q11 attractive, Q11 repulsive.
DEBYE_Q11 = [
    (0.063,0.0224),(0.1364,0.0511),(0.1961,0.0797),(0.248,0.1072),
    (0.3297,0.1584),(0.3962,0.205),(0.4519,0.2474),(0.6467,0.4177),
    (0.7746,0.5442),(0.8719,0.6455),(1.0173,0.8026),(1.1259,0.923),
    (1.213,1.0207),(1.4972,1.3431),(1.6716,1.5412),(1.7984,1.6847),
    (1.9807,1.8898),(2.1123,2.0368),(2.2156,2.1515),(2.5427,2.5087),
    (2.738,2.7168),(2.878,2.8635),(3.0767,3.0687),(3.2185,3.2135),
    (3.3289,3.3256),(4.4759,4.4763)
]

def pair_key(a: str, b: str) -> str:
    return "|".join(sorted((a,b)))

def charge(alias: str) -> int:
    if alias.endswith("+"):
        return 1
    if alias.endswith("-"):
        return -1
    return 0

def parse_db(path: Path):
    species = {}
    pairs = {}
    current = None
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.split("#",1)[0].strip()
        if not line:
            continue
        f = line.split()
        if current is None:
            if f[0] == "species":
                if len(f) != 4:
                    raise ValueError(f"line {n}: malformed species")
                species[f[1]] = (float(f[2]), f[3])
            elif f[0] == "pair":
                if len(f) != 5:
                    raise ValueError(f"line {n}: malformed pair")
                current = {
                    "a": f[1], "b": f[2],
                    "B": float(f[3]), "C": float(f[4]), "rows": []
                }
            else:
                raise ValueError(f"line {n}: unknown keyword {f[0]}")
        else:
            if f[0] == "endpair":
                pairs[pair_key(current["a"], current["b"])] = current
                current = None
            else:
                if len(f) != 3:
                    raise ValueError(f"line {n}: malformed collision row")
                current["rows"].append(tuple(map(float, f)))
    if current is not None:
        raise ValueError("unterminated pair")
    return species, pairs

def interpolate_static_q11(T, pair):
    rows = pair["rows"]
    grid = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    if T <= grid[0]:
        q = vals[0]
    elif T >= grid[-1]:
        q = vals[-1]
    else:
        upper = bisect.bisect_right(grid, T)
        i = upper - 1
        q = vals[i] + (T-grid[i])*(vals[i+1]-vals[i])/(grid[i+1]-grid[i])
    return q * PI * 1.0e-20

def debye_q11(T, Te, ne, alias_a, alias_b):
    b = QE*QE/(8.0*PI*EPS0*KB*T)
    ne_eff = max(ne, DEBYE_NE_FLOOR)
    lambda_raw = math.sqrt(0.5*EPS0*KB*Te/(ne_eff*QE*QE))
    lambda_max = 2.0*DEBYE_TSTAR[-1]*b
    lambda_D = min(lambda_raw, lambda_max)

    tstar = 0.5*lambda_D/b
    tstar = min(max(tstar, DEBYE_TSTAR[0]), DEBYE_TSTAR[-1])

    col = 0 if charge(alias_a)*charge(alias_b) < 0 else 1
    if tstar <= DEBYE_TSTAR[0]:
        reduced = DEBYE_Q11[0][col]
    elif tstar >= DEBYE_TSTAR[-1]:
        reduced = DEBYE_Q11[-1][col]
    else:
        upper = bisect.bisect_right(DEBYE_TSTAR, tstar)
        lower = upper - 1
        reduced = (
            DEBYE_Q11[lower][col]
            + (tstar-DEBYE_TSTAR[lower])
            * (DEBYE_Q11[upper][col]-DEBYE_Q11[lower][col])
            / (DEBYE_TSTAR[upper]-DEBYE_TSTAR[lower])
        )
    scale = PI*lambda_D*lambda_D/(tstar*tstar)
    return reduced*scale

def evaluate(db_path: Path, ne: float):
    species_db, pairs = parse_db(db_path)

    masses_molar = [species_db[s][0] for s in SPECIES_ORDER]
    aliases = [species_db[s][1] for s in SPECIES_ORDER]

    mole_den = sum(y/M for y,M in zip(Y,masses_molar))
    X = [(y/M)/mole_den for y,M in zip(Y,masses_molar)]
    particle_mass = [M/NA for M in masses_molar]
    number_density = P/(KB*T_G)

    nDij = [[0.0]*7 for _ in range(7)]
    for i in range(7):
        for j in range(i,7):
            ai, aj = aliases[i], aliases[j]
            if charge(ai) != 0 and charge(aj) != 0:
                q11 = debye_q11(T_G,T_E,ne,ai,aj)
            else:
                k = pair_key(ai,aj)
                if k not in pairs:
                    raise ValueError(f"missing static pair {k}")
                q11 = interpolate_static_q11(T_G,pairs[k])

            fac = (3.0/16.0)*math.sqrt(
                2.0*PI*KB*(particle_mass[i]+particle_mass[j])
                /(particle_mass[i]*particle_mass[j])
            )
            nd = math.sqrt(T_G)*fac/q11
            nDij[i][j] = nDij[j][i] = nd

    out = {}
    for i,s in enumerate(SPECIES_ORDER):
        denominator = 0.0
        for j in range(7):
            if i == j:
                continue
            Dij = nDij[i][j]/number_density
            denominator += X[j]/Dij
        out[s] = (1.0-Y[i])/denominator
    return out

def self_test(db_path: Path):
    A = evaluate(db_path, NE_A)
    B = evaluate(db_path, NE_B)

    # Neutral aliases must be invariant to electron screening.
    for s in ["O2","O2s","O","Os"]:
        rel = abs(B[s]-A[s])/A[s]
        if rel > 1e-14:
            raise AssertionError(f"neutral oracle ne-invariance failed for {s}: {rel}")

    # Every charged species must show a material screening response.
    for s in ["O2p","Om","Op"]:
        rel = abs(B[s]-A[s])/A[s]
        if rel < 0.05:
            raise AssertionError(f"charged oracle ne sensitivity too small for {s}: {rel}")

    # Formula mutation control: replace mass-fraction numerator by mole fraction.
    species_db,_ = parse_db(db_path)
    Ms = [species_db[s][0] for s in SPECIES_ORDER]
    mole_den = sum(y/M for y,M in zip(Y,Ms))
    X = [(y/M)/mole_den for y,M in zip(Y,Ms)]
    # A wrong numerator changes at least one oxygen/molecular result materially.
    max_num_mut = max(abs((1.0-X[i])/(1.0-Y[i])-1.0) for i in range(7))
    if max_num_mut < 1e-3:
        raise AssertionError("numerator mutation control is not discriminating")

    print("EVR1B_ORACLE_SELFTEST: PASS")
    print(f"ORACLE_A_charged={{s:A[s] for s in ['O2p','Om','Op']}}")
    print(f"ORACLE_B_charged={{s:B[s] for s in ['O2p','Om','Op']}}")
    return 0

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--self-test":
        raise SystemExit("usage: oracle.py --self-test transport_data.txt")
    raise SystemExit(self_test(Path(sys.argv[2])))
