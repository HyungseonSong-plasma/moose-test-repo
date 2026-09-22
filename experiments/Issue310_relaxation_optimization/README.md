# Issue 310 — relaxation-factor optimization

This experiment isolates the fixed-point relaxation factor while freezing the
latest Issue #306 wall09 plasma model and all solver tolerances.

## Fixed clock

```text
chi_e   = 100
chi_h   = 400
dt_h/dt_e = 4
T_final = 80000 tau_epsilon(initial)

electron steps = 800
heavy steps    = 200
```

## Sweep

```text
relax_1x  =  1/(1+chi_e) = 0.009900990099...
relax_10x = 10/(1+chi_e) = 0.099009900990...
relax_50x = 50/(1+chi_e) = 0.495049504950...
```

The third requested value is interpreted as `50/(1+chi)`; `50*(1+chi)`
would be 5050 at chi=100 and is not an under-relaxation factor.

## Frozen physics

The cases inherit Issue #306 wall09 unchanged:

- electron drift + Poisson + electron energy;
- Joule heating + O2 elastic energy loss;
- released heavy transport;
- O2+/O+ Bohm wall loss;
- O- thermal sticking + signed migration;
- standard-MOOSE electron sheath suppression;
- chemistry OFF and RF OFF;
- identical physical horizon, dt, nonlinear tolerances, fixed-point tolerances,
  and `fixed_point_max_its=3000`.

The static contract requires the generated parent and Poisson inputs to be
byte-identical across cases, and the fast-child inputs to become byte-identical
after normalizing the single `relaxation_factor` line.

## Evidence

Each case retains:

- wall-clock elapsed seconds;
- parent potential time series;
- fast-child per-step and cumulative fixed-point iterations;
- final potential/electron/energy/heavy profiles;
- compact runtime failure tail.

The aggregate compares the 10x and 50x cases with the historical 1x rule for
both computational cost and final-profile parity. Solver completion or speedup
alone is not a physics-equivalence claim.
