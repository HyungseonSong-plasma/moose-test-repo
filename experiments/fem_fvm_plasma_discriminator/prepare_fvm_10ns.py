#!/usr/bin/env python3
from pathlib import Path
import prepare_cases_plasma_only as plasma_only

HERE = Path(__file__).resolve().parent
base = plasma_only.base

text = base.fvm()
old_steps = f"  num_steps = {base.NSTEPS}\n"
old_end = f"  end_time = {base.END_TIME:.17g}\n"
if old_steps not in text or old_end not in text:
    raise RuntimeError("Could not locate 100 ns Executioner settings")
text = text.replace(old_steps, "  num_steps = 10\n", 1)
text = text.replace(old_end, "  end_time = 1e-08\n", 1)

out = HERE / "fvm_plasma_discriminator_10ns.i"
out.write_text(text, encoding="utf-8")
print(f"wrote {out}")
print("FVM short discriminator: dt=1 ns, 10 steps, end_time=10 ns")
print("All physics/state/BC/solver settings inherited unchanged from the log-molar 100 ns comparator")
