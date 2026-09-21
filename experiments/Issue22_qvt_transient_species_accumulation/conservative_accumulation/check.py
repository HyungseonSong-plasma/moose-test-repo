#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, math, tempfile
from pathlib import Path

def read_rows(path: Path):
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"empty CSV: {path}")
    out=[]
    for r in rows:
        out.append((float(r["time"]), float(r["w_avg"])))
    return out

def candidate_check(path: Path) -> int:
    rows=read_rows(path)
    max_q_err=0.0
    max_w_err=0.0
    for t,w in rows:
        rho=1.0+t
        q=rho*w
        w_exact=1.0/rho
        max_q_err=max(max_q_err, abs(q-1.0))
        max_w_err=max(max_w_err, abs(w-w_exact))
    print(f"CANDIDATE_MAX_Q_ERROR={max_q_err:.17e}")
    print(f"CANDIDATE_MAX_W_ERROR={max_w_err:.17e}")
    ok=max_q_err <= 1.0e-9 and max_w_err <= 1.0e-9
    print("R22_PRODUCT_EXACT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1

def mutation_check(path: Path) -> int:
    rows=read_rows(path)
    t,w=rows[-1]
    q=(1.0+t)*w
    drift=abs(q-1.0)
    w_const_err=abs(w-1.0)
    print(f"MUTATION_FINAL_Q_DRIFT={drift:.17e}")
    print(f"MUTATION_FINAL_W_CONST_ERROR={w_const_err:.17e}")
    # Expected negative control: rho*dw/dt keeps w approximately constant,
    # therefore rho*w must drift strongly when rho(t)=1+t.
    detected = drift >= 0.25 and w_const_err <= 1.0e-8
    print("R22_LEGACY_MUTATION_DETECTED:", "PASS" if detected else "FAIL")
    return 0 if detected else 1

def self_test() -> int:
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        good=td/"good.csv"
        bad=td/"bad.csv"
        mut=td/"mut.csv"
        good.write_text("time,w_avg\n0,1\n0.1,0.9090909090909091\n0.5,0.6666666666666666\n")
        bad.write_text("time,w_avg\n0,1\n0.5,1\n")
        mut.write_text("time,w_avg\n0,1\n0.5,1\n")
        checks=[
            candidate_check(good)==0,
            candidate_check(bad)!=0,
            mutation_check(mut)==0,
            mutation_check(good)!=0,
        ]
    ok=all(checks)
    print("R22_CHECKER_SELFTEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--mode", choices=["candidate","mutation"])
    ap.add_argument("--csv")
    a=ap.parse_args()
    if a.self_test:
        return self_test()
    if not a.mode or not a.csv:
        ap.error("--mode and --csv are required unless --self-test")
    p=Path(a.csv)
    if a.mode=="candidate":
        return candidate_check(p)
    return mutation_check(p)

if __name__=="__main__":
    raise SystemExit(main())
