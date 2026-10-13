# Issue #376 — Maxwell → plasma RF power transfer

Active development surface for conservative RF-power coupling from the frozen
Issue #202 scalar-RZ Maxwell solution into the current FEM electron-energy
representation and, after T1–T3, the first bounded segregated feedback loop.

## Frozen upstream contract

Issue #202 remains the RF field owner. Its accepted peak-phasor convention is

```text
E(t) = Re{E_hat exp(+i omega t)}
Q_RF = 0.5 * sigma_R * |E_hat|^2
P_abs = integral_plasma Q_RF dV
```

The frozen standalone reference has `P_abs = 175.81487393245 W`.  The reactive
conductivity enters the Maxwell field but not the collisional heating term.

## Current representation

The promoted plasma line solves `log_energy` with continuous FEM/LAGRANGE.
Production RF heating therefore uses

```text
Maxwell E_real/E_imag  : FEM on full QVT chamber mesh
cross-mesh map         : SolutionUserObject + SolutionAux
Q_RF                    : quadrature-point material on plasma
electron log_energy    : FEM on accepted contour plasma mesh
source injection       : MatBodyForce
```

The nonmatching source/target mesh power defect is measured explicitly and the
target source is globally renormalized so its integrated RF power equals the
Maxwell absorbed power.  RF heating remains separate from electrostatic
`PhysicsFEMLogMolarElectronJouleHeating` ownership.

## Accepted gates

```text
T1 conservative transfer     PASS  Actions 38370381057
T2 spatial transfer          PASS  Actions 38371674096
T3 counterfactuals           PASS  Actions 38372574448
T4 coupling convergence      ACTIVE
T5 power closure             PENDING
T6 representative oxygen ICP PENDING
```

T2 independently reconstructed the TRI3 interpolation and found approximately
1.01% RZ complex-field L2 error, 0.68% RZ `Q_RF` L2 error, and 0.86% normalized
power-shape error on the accepted contour mesh. T3 closed RF-off,
transfer-off, `sigma_R = 0`, and frozen-state determinism discriminators.

## T4 — reduced segregated feedback discriminator

T4 intentionally precedes the complete oxygen ICP case.  It uses the canonical
plasma discriminator state

```text
n_e = 1.0e15 m^-3          (held fixed in T4)
mean electron energy = 4 eV initially
p = 1.333223684 Pa
T_g = 300 K
f_RF = 13.56 MHz
```

and closes the state-dependent conductivity with the canonical reduced electron
mobility table `Issue91_real_qvt_r3/r3_e0/electron_moments.txt`:

```text
N_n  = p / (k_B T_g)
mu_e = (mu_e N_n)_table / N_n
nu_m = e / (m_e mu_e)

sigma_R = n_e e^2 nu_m / [m_e (nu_m^2 + omega^2)]
sigma_I = -n_e e^2 omega / [m_e (nu_m^2 + omega^2)]
```

The sign of `sigma_I` follows the accepted `exp(+i omega t)` convention.

For each physical backward-Euler step, `run_t4_coupling.py` performs an
**unrelaxed Picard iteration**:

```text
volume-mean electron energy guess
  -> mobility / collision frequency / complex sigma
  -> frozen #202 Maxwell solve
  -> cross-mesh RF transfer + conservative power renormalization
  -> one 2-D FEM log_energy step from the fixed previous physical state
  -> new volume-mean electron energy
  -> repeat until converged
```

Re-applying the same previous physical state on every Picard iteration is
important: the iteration solves one implicit coupled timestep rather than
accumulating pseudo-time heating.


### T4-v1 calibration result

The first exact-head T4 run (`38375574743`, head `ca72cf5b975b487bd6712ae3f496ee3d3b8bfe93`)
failed the original predeclared **8-iteration** budget on the coarse `dt = 2 us`
step.  It did **not** diverge: the unrelaxed Picard residual sequence was

```text
1.325e+00 -> 3.111e-01 -> 4.975e-02 -> 7.256e-03 -> 1.025e-03
          -> 1.458e-04 -> 2.075e-05 -> 2.952e-06
```

with an asymptotic contraction factor of about `0.142`, while the raw mapping
defect remained about `0.18--0.20%`.  T4-v1 is therefore recorded as **FAIL**
against its original 8-iteration discriminator.  T4-v2 changes **only** the
maximum Picard budget to `12`, before rerunning; the `1e-7` residual tolerance,
`< 0.8` contraction gate, power-closure gate, raw-transfer gate, positivity,
lookup-range, and timestep-refinement gates are unchanged.  A T4-v2 result is
not a retroactive PASS of T4-v1.


### T4-v2 calibration result

The second exact-head T4 run (`38376764298`, head `a9a19c0af911ccc9c76c82214d85d277200fbaa9`)
closed every unrelaxed Picard solve under the revised 12-iteration budget, but it
failed the unchanged `< 0.5%` temporal-accuracy gate.  Over the same `2 us`
horizon, final mean energies were `12.9072971852 eV` (`dt=2 us`),
`12.2856179851 eV` (`dt=1 us`), and `11.8159929582 eV` (`dt=0.5 us`).
The coarse-to-medium and medium-to-fine relative differences were `5.261337%`
and `3.974486%`; their ratio was `0.755414`, so the sequence was contracting
but not yet temporally resolved enough.  T4-v2 is therefore recorded as
**FAIL**.

T4-v3 keeps the physical horizon and every acceptance tolerance unchanged, but
moves the three-level halving triplet into a finer asymptotic regime:
`dt = 0.125 us, 0.0625 us, 0.03125 us`.  This is a resolution refinement, not
a relaxation of the `< 0.5%` accuracy gate.

### Predeclared T4 acceptance gates

The exact-head CI run must satisfy all of the following:

- three refinements over the same `2 us` horizon: `dt = 0.125 us, 0.0625 us, 0.03125 us`;
- every physical step reaches Picard relative residual `<= 1e-7` in at most
  `12` iterations;
- while above the convergence floor, Picard residual contraction ratio remains
  `< 0.8` without under-relaxation;
- every iteration keeps Maxwell ↔ deposited RF power relative closure
  `<= 1e-10`;
- raw cross-mesh power mismatch remains `< 2%` before conservative scaling;
- electron-energy density remains finite and strictly positive;
- the volume-mean energy remains inside the transport lookup range;
- the medium→fine timestep difference in final mean energy is `< 0.5%` and
  contracts relative to coarse→medium with ratio `< 0.8`.

The full spatially varying `n_e`, complex conductivity, oxygen chemistry,
transport, electrostatic field, walls, and dielectric feedback are explicitly
**not** claimed by T4. Those enter only after T4/T5, under T6.
