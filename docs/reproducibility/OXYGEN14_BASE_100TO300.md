# Oxygen14 BASE native 100 → 300 µs reproducibility reference

Historical source commit: `aac65d79e9d41094787e744358ce5fdc4154feae`.
Upstream true native 100 µs run: [42049066748](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42049066748).
Downstream completed 400/1000 W native 300 µs run: [42187714174](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42187714174).

The experiment directory contains the exact original verification helper
(`base14_restart_100to300us.py`), pinned native restart shell wrapper
(`base14_restart_native.sh`), and launch provenance `BASE14_RESTART_100TO300US_LAUNCH.run`.
All are **development-only reproduction materials**, not default workflows.

The verifier requires an upstream native checkpoint and original source/input
archives; it dynamically loads a pinned staged library at
`_restart_library/.github/scripts/oxygen25_restart_chain.py`. These sources and
private rates **are not embedded here**. For full scientific replay, restore the
original pinned source tree/archive and exact inputs with permission. Copying
only these files to `main` does *not* make the original proprietary/native
experiment runnable without its pinned dependencies.

The regression at `tests/test_base14_restart_local_progress.py` verifies the
restart-local MOOSE step counter must begin at 0 and advance monotonically,
while absolute physical time must start at 100 µs and end at 300 µs.
The previous erroneous requirement that local step exceed upstream 460 is not
valid for a new process. This is a **contract-level replay regression**,
distinct from native solver verification.

Do not add a new noncanonical GitHub workflow, change Oxygen14 chemistry or RF
power, accept private rate tables, or interpret a green CI as scientific parity.
`SCIENCE_HOLD` remains.
