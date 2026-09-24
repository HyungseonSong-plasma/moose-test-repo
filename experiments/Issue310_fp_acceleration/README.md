# Issue #310 qualified Gummel baseline

Issue #310 is closed with the Gen34 optimized endpoint promoted as the default starting point for future Gummel/MultiApp performance work.

## Canonical source

- branch: `qualified/issue310-gummel-optimized`
- exact SHA: `cdba1cba025da3c8442c0ad2993aeccab0111732`
- generator: `control_seq34_relax2x_reference_input.py`
- case: `optimized_endpoint_20ns`

The branch is intentionally preserved separately from `main` because the experimental history diverged substantially from current main. New work should consume the exact qualified SHA rather than merge the whole experimental branch.

## Default numerical configuration

```text
architecture               = TransientMultiApp + Transient Poisson
no_restore                 = true
banded correction          = bandwidth 5
relaxation_factor          = 0.45
fixed_point_algorithm      = steffensen
transformed variable       = potential_from_poisson
delta_phi_abs_tol          = 1e-6 V
compute_scaling_once       = true
fp_anchor_csv              = disabled
scalar timestep CSV        = retained
spatial profiles           = FINAL only
```

Physics remains the qualified Issue306 Sequence08 thermal/time-aware, chemistry-off, RF-off lane.

## Qualification result

Controlled 19.941 ns benchmark, 352 electron steps / 88 heavy steps, paired AB/BA on the same runners:

```text
relax_2x reference mean runtime = 30.39 min
optimized mean runtime          =  2.44 min
geometric-mean speedup          = 12.448x
wall-time reduction             = 91.97%

reference FP total              = 140,525
optimized FP total              =   9,102
reference FP / electron step    = 399.22
optimized FP / electron step    =  25.86
FP-work reduction               = 93.52%
```

Final-state profile differences remained at approximately 1e-8 normalized scale; final average-potential difference was 8.31e-8 V. The maximum transient potential-history difference was about 7.2e-6 V.

## Consumer rule

Future Gummel/MultiApp optimization experiments must read `qualified_baseline.json` and start from its `canonical_source.sha` unless a later qualification explicitly supersedes it.

The historical `relax_2x` configuration is retained only as the controlled reference, not as the default production/performance configuration.
