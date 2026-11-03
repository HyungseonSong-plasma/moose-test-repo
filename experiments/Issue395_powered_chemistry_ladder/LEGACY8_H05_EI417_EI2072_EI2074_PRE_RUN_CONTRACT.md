# Oxygen ICP: EI-2074 pre-run design contract

**Status: PREPARED / NOT DISPATCHED / SCIENCE_HOLD** — 2026-11-03.

## Controlled single-reaction expansion

Reference baseline: **Legacy8** (8 channels, Run 41547927512).
Successive controlled experiments:

| Experiment | Count | Reference run |
| --- | ---: | --- |
| Legacy8 | 8 | 41547927512 |
| Legacy8 + H05 | 9 | 41606747216 |
| Legacy8 + H05 + EI-417 | 10 | 41607701578 |
| Legacy8 + H05 + EI-417 + EI-2072 | 11 | 41609427736 |
| Legacy8 + H05 + EI-417 + EI-2072 + EI-2074 | **12** | **Not run** |

The 12-channel variant adds **only EI-2074** compared with the 11-channel
parent. Reuse the **same pinned PhysicsApp source SHA**
`8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab`,
400 W/1000 W RF Maxwell coupling, existing mesh, latest initial-mixture EEDF
lookup, 200 sccm inlet, wall model, initial seeds and 0–100 microsecond
461-time-point schedule. Fresh runs (no restart from a different Chemistry).

## Reaction and original rate evidence

EI-2074:

\[
e + O_2(a^1\Delta_g) \longrightarrow O^+ + O(^3P) + 2e.
\]

- Electron net gain: **+1 per event** (one incident, two emitted).
- Ground-state atomic oxygen gain: **+1 per event**.
- Positive atomic oxygen ion gain: **+1 per event**.
- Excited molecular oxygen loss: **-1 per event**.
- Model electron energy sink: **16.023 eV/event**.
- Excited target is existing solver state **w_O2s**.
- O+ is **log_nop**, O(3P) is **w_O**, e- is **log_ne**, electron
  energy is **log_energy**; neutral gas mass closure goes into **p**.
- This channel does **not** create O2+, O-, or a new O2(X) PDE.

Existing private HPEM provenance: `O2ex.dat`, Process 18,
`SPECIAL NUMBER=2074`, threshold 16.023 eV, 1001-point cross section.
Existing prepared 100-point table:
`EI-2074_O2_a1Delta.txt`. Use the **original table from the existing**
GitHub Actions `OXYGEN24_RATES_TAR_XZ_B64` secret, restore it privately
on the runner, validate the full original set of 19 rate files and
SHA-256-match this table in the native variant manifest.
Never synthesize a replacement rate, substitute EI-417, or publish private
rate bytes in logs/artifacts. The numerical source is not proof of an
independently measured state-resolved cross section.

## Single-owner source and conservation contract

`c_O2a = rho_neutral * w_O2s / 0.032` mol/m3.
`PhysicsElectronImpactRateMaterial` evaluates a **single**
`R_EI2074` [mol/(m3 s)] with `mean_en_solved`,
`n_e_physical`, and `c_O2a_EI2074`. Project all solver source terms
from that one progress owner.

| Equation / source | EI-2074 contribution |
| --- | --- |
| `log_ne` | `+R` [mol/(m3 s)] |
| `log_nop` | `+R` [mol/(m3 s)] |
| `w_O2s` | `-0.032 R` [kg/(m3 s)] |
| `w_O` | `+0.016 R` [kg/(m3 s)] |
| `p` neutral fluid | `-0.016 R` [kg/(m3 s)] |
| `log_energy` | `-16.023 R` [established model units] |

The following algebraic invariants apply for each progress event:

- Heavy-particle mass: `-0.032 R + 0.016 R + 0.016 R = 0`.
- Neutral fluid mass: `-0.032 R + 0.016 R = -0.016 R`.
- Oxygen nuclei: 2 O nuclei on both sides.
- Charge: `O+ (+R) - electron (+R) = 0`; reactant charge -1,
  product charge +1-2=-1.
- Independent rate owner count: **exactly one**.
- Reserved parser symbols such as `e` are forbidden.
- Inherited EI-407, H05, EI-417, and EI-2072 source owners remain unchanged.
- Exclude all private rate files from downloadable artifacts.

## Before running

The next expressly authorized experiment must pass:

1. **P0**: exact pinned source, Python harness self-tests, original secret
   lookup inventory (EI-407, EI-417, EI-2072, EI-2074), finite nonnegative
   ordered 100-point tables, clean generated overlays and parsing preflight.
2. **P1**: native PhysicsApp build with unchanged Maxwell coupling.
3. **P2**: native `--check-input` with the guarded chemistry overlay list.
4. **P3**: fresh 400 W and 1000 W, 0–100 microsecond native transient.
5. **P4**: actual final 100-us Exodus, plasma.csv, checkpoint and
   source/charge/mass closure, complete provenance and sanitized archives.

After the run, compare the 11-channel EI-2072 parent against this 12-channel
case for `n_e`, `n_O-`, `n_O+`, `n_O2+`, `n_O`, `n_O2`, `n_O2(a)`,
`Te` and `P_abs`, plus `R_EI2074` integrated source and the
electron-production budget (EI-16, EI-20, H05, EI-417, EI-2072, EI-2074).
Volume-averaged trends and local peak changes should both be inspected.
P4 completion does **not** establish steady state or scientific acceptance.

## Deliberate dispatch interlock

Prepared workflow:

`.github/workflows/oxygen-legacy8-h05-ei417-ei2072-ei2074-400-1000w-100us.yml`

A push to this dedicated branch launches the simulation **only** when the
path `experiments/Issue395_powered_chemistry_ladder/EI2074_LAUNCH_GATE.run`
is added or edited. The marker file **is intentionally not present**.
Script, overlay, and document commits do not trigger the new workflow.
The optional manual workflow_dispatch entry remains a later explicit action.

This contract is the **pre-run** output; it is not a claim that native
P0–P4 has already run. Parent experiments may be in progress or still
scientifically unvalidated. H05 birth-electron energy remains unresolved
and is explicitly retained as a science HOLD issue.
