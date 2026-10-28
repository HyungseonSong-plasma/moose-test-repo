# Oxygen ICP 400/1000 W, O2+ DR OFF/ON — zero initial O(3P)

**Status:** separate scientific sensitivity experiment. Do not merge production chemistry.

## Intervention

Repeat the exact earlier four arms (400 W OFF, 400 W ON, 1000 W OFF,
1000 W ON) from fresh state, on the same 27-face Graded L1, 460-step,
100 microsecond Maxwell/ICP model, except initial atomic O mass fraction.

The original generated input's direct FV variable is:

    [w_O]
      type = INSFVScalarFieldVariable
      initial_condition = 0.10309278350515465

The zero-O treatment replaces that one value with 0.0 after
the original input generator, time-grid and D1 instrumentation have finished,
using set_zero_initial_atomic_o.py; all cases use the same treatment.
The generated O2 residual is w_O2 = 1 - w_O2s - w_O - w_Os.

- Original O2 mass fraction: 0.7216494845360825
- New O2 mass fraction: 0.8247422680412371
- O2s and Os original values: 0.051546391752577324 and 0.12371134020618557.
- Charged/electron initial conditions, boundary feed, geometry, solver, RF,
  DR kinetic fit and all active legacy reaction operators are unchanged.
- Only O(3P)-like solved species O is zero; pre-existing Os (excited
  O(1D)) remains nonzero, so this is not a zero-all-atomic-oxygen state.

Both prepare and subsequent build/check/solve/audit stages enforce
an exact single-block zero w_O initialization. Mutation tests fail on
any noncanonical original O mass fraction, missing O2 closure, duplicate
O state block, or nonzero replacement.

## Execution and comparison

P0 tests both the old DR chemistry and the new initial-state patch.
P1 compiles the exact PhysicsApp.
P2 checks actual zero-O inputs for all four arms (DR ON additionally
checks the separate DR overlay).
P3 executes four independent full 100-us physics-opt trajectories.
P4 independently audits the full 27-face D1 charge/current record.
P5 computes original chemistry/power/D1 checks and the ON/OFF DR effect.

Each case uses one exact source commit, NOT previous 0.10309-O data.
Old data remain immutable control context, not valid OFF controls for this
new initial-state experiment.

Use final O mass integral over actual plasma RZ volume, convert to
volume-average number density using N_A/0.016 kg mol-1, and compare:
1. n_O(t), O ion and electron/energy trajectories across all four arms.
2. Absolute and relative (ON-OFF) at 400 and 1000 W with common time axis.
3. Difference in n_O(t) from the previous nonzero-initial-O experiment,
   explicitly labelled different initial composition, not isolated RF effect.
4. O2p/DR progress, O mass-production integral, power-delivery accuracy,
   solver completion and charge/current source conservation.

Scientific HOLD remains because the DR thermal rate is extrapolated to
ICP conditions, excited product branching is aggregated into O-equivalent
and the electron-energy source uses a removed-mean-energy proxy.
Numerical pass does not establish validated chemistry accuracy.
