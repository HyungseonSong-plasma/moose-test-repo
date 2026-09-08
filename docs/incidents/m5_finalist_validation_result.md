# M5 Finalist Validation Result

**Status:** production convergence strategy selected  
**Scope:** full coupled solved-potential O2+ bulk drift + surface wall loss + migration wall loss

## Finalist strategies

A. `automatic_scaling = false` with explicit `w_O2_plus` scaling  
B. `ReferenceResidualConvergence` for `w_O2_plus`, AND-combined with the global convergence gate while keeping `automatic_scaling = true`

## Executed regime matrix

Both strategies were tested across seven full-coupled regimes:

- initial-potential scale `s = 0, 0.5, 1.0`;
- timestep `dt = 5e-6, 1e-5, 2e-5`;
- ion mobility `mu_i = 0.005, 0.01, 0.02`.

Every case included:

- solved electrostatic potential;
- bulk `QPXFVElectrostaticDrift`;
- surface wall loss;
- migration wall loss;
- global ion-mass conservation check;
- migration directionality check;
- positivity check.

## Result

| Strategy | All solved | All physics checks | Max balance error | Mean nonlinear iterations | Max nonlinear iterations |
|---|:---:|:---:|---:|---:|---:|
| manual explicit scaling | yes | yes | `1.400596e-12` | `1.86` | `2` |
| species-aware reference residual | yes | yes | `1.400596e-12` | `1.86` | `2` |

The two strategies are numerically indistinguishable over the tested matrix.

All cases satisfy:

- closure `C = (-dm/dt)/G = 1.000000`;
- migration left boundary approximately zero;
- migration right boundary positive;
- positive mass fraction;
- nonlinear iteration count at most two.

## Production decision

Select **species-aware `ReferenceResidualConvergence`** as the production default.

Rationale:

1. It directly encodes the multiphysics requirement that species convergence must not be hidden by a dominant electrostatic residual.
2. It retains automatic scaling rather than depending on a fixed global manual-scaling policy.
3. It has no measured nonlinear-iteration penalty relative to the manual-scaling finalist in the executed regime matrix.
4. It naturally extends to additional species/physics by adding subsystem convergence groups and combining them with `ParsedConvergence`.
5. The manual explicit-scaling strategy remains a useful fallback and diagnostic control, not the preferred default.

## Promotion rule

Before closing M5 completely:

1. encode the selected reference-residual convergence pattern in permanent regression inputs;
2. promote the solved-potential zero-IC wall/full-coupled cases from diagnostic to canonical after they pass under the selected strategy;
3. preserve the mass-balance acceptance gate at `1e-8` or tighter;
4. retain a manual-scaling comparison only as diagnostic evidence, not as the primary production configuration.

## Root cause restated

The wall-migration physics was not defective. The original failure was caused by premature global nonlinear convergence, amplified by automatic-scaling/global-norm interaction, allowing the dominant electrostatic solve to satisfy the global relative criterion before the species-wall coupling completed its second nonlinear correction.
