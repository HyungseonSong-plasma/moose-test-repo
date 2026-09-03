# Issue #31 — R4-Q0 all-ground solved-Poisson discriminator

This package runs the first bounded R4 discriminator from the accepted Issue #91 R3 control.

## Frozen Phase-1 scope

```text
accepted R3 heavy + electron transport     PRESERVED
prescribed transport field                 E = 0 control
physical volume charge                     ON
solved potential_plasma                    ON
electrostatic transport feedback           OFF
surface accumulated charge (sigma_s)       OFF
secondary emission                         OFF
volumetric reactions                       OFF
```

The purpose is to isolate physical charge construction and the Poisson solve before enabling self-consistent drift feedback.

## Electron representation

The accepted R3 normalization remains mandatory:

```text
solver unknown:       n_e == n_hat ~ O(1)
physical density:     n_e_physical = n_ref*n_hat
n_ref:                1e16 m^-3 in the accepted control
```

The Poisson charge material therefore consumes `n_e_physical`, never the normalized solver state directly.

## Charge construction — C0

For the current oxygen charged-heavy set:

```text
O2p : z = +1, M = 0.032 kg/mol
Om  : z = -1, M = 0.016 kg/mol
Op  : z = +1, M = 0.016 kg/mol
```

with

```text
n_k = rho*w_k*N_A/M_k
rho_q = e*(n_O2p - n_Om + n_Op - n_e_physical)
```

`QPXPlasmaChargeDensityMaterial` owns `charge_number_density`, `charge_density`, and `poisson_charge_source`.

## Poisson problem

The plasma solve is

```text
-div(eps_r*grad(phi)) = rho_q/eps_0
E = -grad(phi)
```

with `eps_r = 1` in the plasma block for this control.

The qvt input does not have a single pre-existing sideset that represents every side of the plasma subdomain. The recipe creates `r31_plasma_all_boundary` around the complete plasma subdomain and applies

```text
phi = 0
```

to that entire sideset. This is an intentional all-ground Phase-1 simplification, not the final reactor electrostatic boundary map.

Particle/species boundary conditions remain those of accepted R3. Grounding refers only to the electrostatic potential.

## Surface accumulated charge

Canonical terminology is:

```text
accumulated charge == surface accumulated charge == surface charge state sigma_s
```

` sigma_s ` is OFF in this package. No current leaving the volume is silently converted into surface storage. Dynamic `sigma_s` is owned by the later dielectric surface-charge work.

## Gauss-law evidence — C1

The input records:

```text
r31_charge_integral
  = integral_Omega rho_q dV

r31_gauss_flux_reduced
  = integral_boundary (-eps_r*grad(phi).n) dA

r31_gauss_flux_charge
  = eps_0 * r31_gauss_flux_reduced
  = integral_boundary eps_0*eps_r*E.n dA
```

The runner reports

```text
R_G = r31_gauss_flux_charge - r31_charge_integral
relative_defect = |R_G| / max(|Q_flux|, |Q_volume|)
```

The first controlled Q0 run is used to establish the numerical defect scale. The runner deliberately does not hard-code a universal Gauss-law tolerance before that measurement exists.

## Run

```bash
git pull

python -m experiments.Issue31_r4_q0_all_ground.run \
  --qpx "$QPX_OPT" \
  --results-root "$PWD/r4_results"
```

The bounded queue is:

```text
canonical construction/audit
-> qpx-opt --check-input
-> one R4-Q0 runtime
-> preserved #91 physical invariant checker
-> C1 Gauss-law measurement
```

A construction-clean, converged run with the required observables terminates as:

```text
ISSUE31_R4_Q0_STATUS: R4_Q0_EVIDENCE_READY
```

`R4_Q0_EVIDENCE_READY` is not yet scientific R4 PASS. Return the complete directory printed as `ISSUE31_R4_Q0_ROOT`; the measured Gauss-law defect must be interpreted before self-consistent transport feedback is enabled.

## Next gate

If Q0/C1 is accepted, the next bounded step will replace the zero prescribed field in the selected charged-particle transport paths with `potential_plasma` and add C2 global dynamic charge conservation:

```text
Delta Q_volume + integral_dt integral_boundary J_q.n dA = 0
```

Surface accumulated charge remains OFF until its separate `sigma_s` phase is explicitly activated.
