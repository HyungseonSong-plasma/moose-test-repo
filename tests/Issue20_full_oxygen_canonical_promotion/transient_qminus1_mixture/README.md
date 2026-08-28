# R14 EVR1-D — transient seven-species Q-1 mixture

## Purpose

This standalone diagnostic is the final internal tranche of parent EVR1 for Issue #14.

It solves six FV mass fractions:

- O2s
- O2p
- O
- Om
- Op
- Os

and constrains:

```text
O2 = 1 - (O2s + O2p + O + Om + Op + Os)
```

The production `QPXThermalDiffusionMaterial` supplies all seven `D_mix_k`.
Each solved species uses:

- `QPXFVMassFractionTimeDerivative`
- `QPXFVMixtureAveragedDiffusion`

The test intentionally omits bulk advection, reactions, electric migration and Poisson
so transient Q-1 closure can be localized cleanly. Active thermal-gradient behavior is
already isolated by EVR1-C.

## Thermodynamic acceptance

```text
sum(Y_k) = 1
0 <= Y_k <= 1
0.016 <= Mn <= 0.032 kg/mol
rho = p Mn / (R T)
R = 8.31446 J/(mol K)
p = 13.332 Pa
T = 600 K
```

EVR1-D v2 applies `TimeDerivativeAux` directly to the six solved nonlinear
mass-fraction variables. The resulting `dY_k/dt` fields feed an explicit
chain-rule `dMn_dt_model`, followed by

```text
drho_dt_model = p/(R T) * dMn_dt_model
```

This replaces the v1 invalid probe that attempted to differentiate `Mn_out`
and `rho_out` auxiliary output copies.

The checker excludes time=0 from physical acceptance and independently verifies:

```text
drho_dt = p/(R T) * dMn_dt
```

plus CSV finite-difference parity for both `Mn` and `rho`.

## Install

From `/home/songhyeongseon/projects/qvt3d/qpx/temp`:

```bash
rm -rf test_workspace/heavy_transport/r14_transient_mixture_evr1d
tar -xzf R14_EVR1D_transient_mixture_standalone_v1.tar.gz
```

## Run

```bash
./run_test.sh heavy_transport/r14_transient_mixture_evr1d
```

## Expected top-level result

```text
PREPARE    : PASS
CHECK-INPUT: PASS
SOLVE      : PASS
CHECK      : PASS
```

Transport-data SHA-256:

```text
2fa7988c79f6ea23ebdd50e6d1d7fc5018dc8854a27459511ec95c94ebe7ff3d
```

## v2 correction

The first v1 production solve passed, but the checker showed:

```text
MAX_RHO_FD_REL_ERROR=1
MAX_MN_FD_REL_ERROR=1
MAX_ABS_DMN_DT=0
MAX_ABS_DRHO_DT=0
```

while mass closure and EOS remained healthy. The failure was localized to the
derivative-observation harness. MOOSE only provides `TimeDerivativeAux` for
functors with implemented time derivatives; v2 therefore differentiates the
six nonlinear solved variables directly and constructs `dMn/dt` and `drho/dt`
by chain rule.

Activate the MOOSE/QPX conda environment before running so AD FParser JIT has
the runtime environment used by the current local QPX setup.

## v3 temporal-consistency gate

The v2 ~1.8% `Mn`/`rho` secant discrepancy is retained as a diagnostic only.
It is a finite-dt difference between a nonlinear secant and a continuous
current-state chain derivative.

The canonical discrete gate is now

```text
S = 1/Mn
```

because `S` is linear in the constrained seven-species composition. Therefore
its backward finite difference must match the BE derivative assembled directly
from the six solved mass-fraction derivatives. No timestep or physics parameter
was changed to obtain this test.

## v4 execution-order fix

v3 revealed a one-timestep scheduling lag: each `invMn_dot_model(t_n)` matched
the finite-difference derivative from the previous interval.

The cause was not the derivative formula. Direct `TimeDerivativeAux` kernels
and the derived `FunctorAux` copy were both running at `TIMESTEP_END`, so the
derived Aux path had an unprotected same-stage dependency.

v4 removes that dependency. The six direct `dw_k/dt` Aux fields are still
computed by MOOSE at timestep end, but `invMn_dot_model`, `dMn_dt_model`, and
`drho_dt_model` are evaluated directly by functor postprocessors afterwards.
The checker also independently reconstructs `d(1/Mn)/dt` from the four
atomic-family `dw_k/dt` averages.
