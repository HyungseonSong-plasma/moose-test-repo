"""Combined prepare driver for Issue #310 Gen16."""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = {
    "state": ROOT / "control_seq16_state_jacobian.py",
    "relax": ROOT / "control_seq16_relax.py",
}

def run(flag: str) -> None:
    for key in ("state", "relax"):
        cp = subprocess.run([sys.executable, str(SCRIPTS[key]), flag], check=False)
        if cp.returncode:
            raise SystemExit(cp.returncode)
    print(f"ISSUE310_GEN16_COMBINED_{flag[2:].upper()}: PASS")

def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--p0", action="store_true")
    ap.add_argument("--p1", action="store_true")
    ap.add_argument("--p2", action="store_true")
    args=ap.parse_args()
    if args.p0: run("--p0")
    elif args.p1: run("--p1")
    elif args.p2: run("--p2")
    else: ap.error("choose --p0/--p1/--p2")

if __name__=="__main__":
    main()
