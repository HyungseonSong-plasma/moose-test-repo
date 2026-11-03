# Legacy8 + H05 + EI-417 + EI-2072 — pre-run design contract

Status: **PREPARED / NOT DISPATCHED / SCIENCE_HOLD** (2026-11-03).

## Controlled baseline and single difference

- Fixed reference: Legacy8 / Run 41547927512 (8 channels).
- Parent experiment: Legacy8 + H05 + EI-417 / Run 41607701578 (10 channels).
- Experimental variant: parent plus **one channel**, EI-2072, for 11 channels total.
- Power targets: **400 W** and **1000 W**. Fresh 0–100 microseconds with the established
  461-point TimeSequenceStepper, Maxwell RF coupling, 200 sccm inlet, latest 23-xsec
  initial-mixture EEDF transport, wall setup, geometry and starting conditions unchanged.
- Fixed original PhysicsApp reference: `8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab`.
- No baseline or parent source shall be mutated. This branch carries only a new
  harness and a new gated workflow.

## Kinetics and state ownership

`EI-2072: e + O2(a1Delta) -> O2+ + 2e`, net **+1 electron**.
Use **only** `EI-2072_O2_a1Delta.txt` from the GitHub Secret
`OXYGEN24_RATES_TAR_XZ_B64` restored privately during the job.
The 100-point rate file must pass the existing
`build_oxygen_24_source_overlay.validate_files` validation.
A separate SHA-256 is recorded in manifests; the private bytes are not committed,
logged, or archived.

Electron energy loss per event: **11.08 eV** in the pre-existing oxygen chemistry
definition. This is a model-specific value, not independently validated physics.

Map existing states without introducing new species:

| Entity | Existing state | Stoichiometric contribution |
| --- | --- | --- |
| e- | `log_ne` | +1 mol/mol event (net) |
| O2(a) | `w_O2s` | -0.032 kg/mol event |
| O2+ | `log_ni` | +1 mol/mol event |
| neutral gas mass | `p` | -0.032 kg/mol event |
| electron energy | `log_energy` | -11.08 eV/mol progress |

Concentration of the excited O2 target:
`c_O2a = rho_neutral * w_O2s / 0.032` mol/m3.
Unique progress owner:
`PhysicsElectronImpactRateMaterial(reaction_progress=R_EI2072)`,
using `mean_en_solved`, `n_e_physical`, and `c_O2a_EI2072`.
`R_EI2072` is mol/(m3 s). All source kernels and diagnostics derive from
that same progress owner, and no additional neutral O2 equation is created.

## Mass, charge and energy checks

For each mole of reaction progress:

- Oxygen nuclei: 2 on each side.
- Charge (particle basis): left -1; right +1-2=-1.
- Net electron source +R and O2+ source +R imply
  `S_charge = S_O2p - S_e = 0`.
- Heavy mass `S_O2a + S_O2p = -0.032R+0.032R = 0`.
- Neutral fluid mass `S_neutral = -0.032R` equals the neutral O2a loss.
- Electron energy `S_energy = -11.08R` in the established convention.

The overlay must pass parsing preflight, avoid reserved parsed-functor symbol
`e`, and contain exactly one kinetic owner and two FE energy/electron source owners.

## Before any 100-us run

1. Check Python syntax, harness self-test, exact parent chemistry ordering,
   and all 19 private tables (EI-407, EI-417, EI-2072 specifically).
2. Prepare fresh 400-W and 1000-W cases using the inherited harness.
3. Run `bin/physics.py preflight` for each overlay and Python provenance gate.
4. Build the pinned PhysicsApp in the native environment.
5. Execute native `--check-input` using the guarded replay argument patch.
6. Only when explicitly authorized, run the 0–100-us P3 native transient.
7. Preserve 100-us checkpoint, postprocessor CSV, pre/post provenance, and restart inputs
   **excluding** every private rate table. Validate P4 only after actual P3 success.

**Important: pre-run design and source-level checks are not P1/P2/P3 execution evidence.**
Do not claim scientific acceptance from a green CI result.

## Intentional launch interlock

The new workflow file is:

`.github/workflows/oxygen-legacy8-h05-ei417-ei2072-400-1000w-100us.yml`.

A push to this preparation branch triggers that workflow **only when**
`experiments/Issue395_powered_chemistry_ladder/EI2072_LAUNCH_GATE.run` changes.
**This marker file is deliberately absent from the current branch.**
Adding/editing the script, contract or workflow does **not** launch a simulation.

The workflow also includes a manual `workflow_dispatch` trigger for authorized use
when GitHub makes the workflow available. Launch requires a subsequent explicit
instruction and must not be inferred from completion of this design document.

## Comparison and acceptance after a future completed run

Compare EI-2072 to the completed 10-channel parent separately at 400/1000 W:
`n_e`, `n_{O-}`, `n_{O2+}`, `n_{O+}`, `n_O`, `n_{O2}`,
`n_{O2(a)}`; time histories of `P_abs` and `Te`.
Calculate volume-integrated `R_EI2072` and compare with EI-16, EI-20,
EI-417 and H05 electron source budgets. Record peak and end-point percent
changes; inspect charge, heavy mass and neutral mass closure residuals.
The new chemistry remains optional until sensitivity and physical validity
are reviewed.

## Explicit caveats

- The parent H05 birth-electron energy convention remains unresolved.
- Mean-energy-based private lookup does not establish independent state-resolved
  experimental validation for EI-2072.
- A completed 0–100-us transient is not necessarily a converged steady state.
