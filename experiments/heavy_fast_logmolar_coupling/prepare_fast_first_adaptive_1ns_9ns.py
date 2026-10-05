#!/usr/bin/env python3
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORRECTIONS = int(os.environ.get("CORRECTIONS", "5"))

if CORRECTIONS < 1:
    raise RuntimeError("CORRECTIONS must be >= 1")

# Start from the already-qualified fast-first block-correction generator at 1 ns.
os.environ["ION_DT_NS"] = "1"
os.environ["CORRECTIONS"] = str(CORRECTIONS)
subprocess.run(["python3", "prepare_fast_first_matrix_case.py"], cwd=HERE, check=True, env=os.environ.copy())

paths = [
    HERE / "heavy_parent.i",
    HERE / "fast_child.i",
    HERE / "electron_poisson_stage.i",
]

# Two physical cycles at exact target times:
#   t0 = 0
#   t1 = 1 ns    -> dt1 = 1 ns
#   t2 = 10 ns   -> dt2 = 9 ns
# The same sequence is retained on all three executioners, but the OUTER fast
# MultiApp is not allowed to subcycle. The parent therefore supplies each
# physical dt explicitly (1 ns, then 9 ns) to the fast child. This avoids the
# child independently trying to rediscover its next target time and producing
# dt=0 on the second parent call.
TIME_SEQUENCE = "0 1.0e-9 1.0e-8"


def make_adaptive_two_cycle(text: str, label: str) -> str:
    # The matrix generator leaves a fixed 1 ns executioner with one physical step.
    tokens = [
        "  dt = 1e-09\n",
        "  dtmin = 1e-09\n",
        "  dtmax = 1e-09\n",
        "  end_time = 1e-09\n",
    ]
    # Depending on float formatting from the generator, accept the explicit 1.0e-9 form too.
    alternatives = {
        "  dt = 1e-09\n": ["  dt = 1.0e-9\n"],
        "  dtmin = 1e-09\n": ["  dtmin = 1.0e-9\n"],
        "  dtmax = 1e-09\n": ["  dtmax = 1.0e-9\n"],
        "  end_time = 1e-09\n": ["  end_time = 1.0e-9\n"],
    }
    for token in tokens:
        if token in text:
            text = text.replace(token, "", 1)
            continue
        found = False
        for alt in alternatives[token]:
            if alt in text:
                text = text.replace(alt, "", 1)
                found = True
                break
        if not found:
            raise RuntimeError(f"{label}: fixed timestep token not found: {token.strip()}")

    # The split generator adds num_steps=1. Remove it so the time sequence controls
    # both physical cycles. A generated fast input may already have another limit;
    # only remove the first one in the Executioner.
    if "  num_steps = 1\n" not in text:
        raise RuntimeError(f"{label}: num_steps = 1 not found")
    text = text.replace("  num_steps = 1\n", "", 1)

    exec_marker = "[Executioner]\n  type = Transient\n"
    if exec_marker not in text:
        raise RuntimeError(f"{label}: Executioner marker not found")
    insert = (
        "[Executioner]\n"
        "  type = Transient\n"
        "  start_time = 0\n"
        "  end_time = 1.0e-8\n"
        "  [TimeStepper]\n"
        "    type = TimeSequenceStepper\n"
        f"    time_sequence = '{TIME_SEQUENCE}'\n"
        "  []\n"
    )
    text = text.replace(exec_marker, insert, 1)
    return text

for path in paths:
    text = path.read_text(encoding="utf-8")
    text = make_adaptive_two_cycle(text, path.name)
    text = text.replace("output_matrix/", "output_adaptive/")
    path.write_text(text, encoding="utf-8")

# Parent owns the adaptive physical timestep. Disable outer MultiApp subcycling
# so TransientMultiApp advances the fast child by the parent's supplied dt rather
# than asking the child's TimeStepper to march independently to the target time.
parent_path = HERE / "heavy_parent.i"
parent = parent_path.read_text(encoding="utf-8")
ma_start = parent.find("[MultiApps]\n")
exec_start = parent.find("[Executioner]\n", ma_start)
if ma_start < 0 or exec_start < 0:
    raise RuntimeError("parent coupling region not found")
region = parent[ma_start:exec_start]
if region.count("execute_on = TIMESTEP_BEGIN") != 3:
    raise RuntimeError("expected exactly three TIMESTEP_BEGIN outer coupling flags")
if region.count("sub_cycling = true") != 1:
    raise RuntimeError("expected exactly one outer fast MultiApp with sub_cycling = true")
region = region.replace("sub_cycling = true", "sub_cycling = false", 1)
parent = parent[:ma_start] + region + parent[exec_start:]
parent_path.write_text(parent, encoding="utf-8")

print("prepared adaptive fast-first two-cycle diagnostic")
print(f"  fixed-point corrections per physical cycle: {CORRECTIONS}")
print("  cycle 1: t=0 -> 1 ns,  dt=1 ns")
print("  cycle 2: t=1 -> 10 ns, dt=9 ns")
print("  ordering each cycle: [energy -> electron+Poisson] x corrections -> heavy")
print("  heavy state frozen during each fast correction block")
print("  previous-cycle fast/heavy state is reused in cycle 2")
print("  outer fast MultiApp sub_cycling: false")
print("  parent supplies physical dt directly: 1 ns, then 9 ns")
