# Boltzmann P0-3: positive conservative subcell EEPF, growth Q and actual M6b Picard (2026-10-29)

## Scope and provenance

Child Draft PR #413 of parent Draft PR #408, tracked in issue #412. All new
numerical experiments here use **first-party synthetic** cross-section
tables. This is not BOLSIG+ 07/2024 / LXCat Ar process parity, and neither
the private cross-section data nor BOLSIG+ output arrays are committed.

Actual compiled C++ source validation: commit
`60f2179823b0f2bbbd7247c279b16204bbb1fe7a`,
[Repository CI run 40888129833](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40888129833),
job `Native Boltzmann EEPF development controls`, step
`P0-3 conservative reconstructed growth operator and actual M6b Picard eigen re-solves (synthetic)`,
**SUCCESS** with `g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic`.
`Public immutable Physics runtime smoke` also **SUCCESS**.
Full `validate` status must be checked separately; no blanket CI success
claim is inferred from the C++ job alone.

The first CI attempt [40887679040](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40887679040)
failed with `invalid subcell integral domain`: rate evaluation visited
ionization donors wholly below threshold. The fix `38203b9a6515`
preserves the legacy empty-interval = zero convention; subsequent run
[40887902886](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40887902886)
passed the new C++ test. The final run adds an independently measured
nominal-tolerance Picard convergence check.

## Numerical method

Each donor FV cell `i` has edges `a_i,b_i`, cell-constant reference
`f_i` and electron-number mass

```text
M_i  = integral(a_i,b_i) sqrt(E) dE
mu_i = integral(a_i,b_i) E sqrt(E) dE / M_i
f_i(E) = f_i * [1 + s_i * (E - mu_i)]
```

The slope `s_i` is a minmod-limited neighbor secant (one-sided at
domain endpoints), additionally bounded by
`-1/(b_i-mu_i) <= s_i <= 1/(mu_i-a_i)`. Hence the reconstructed
`f_i(E)` is nonnegative throughout its donor cell and its exact
sqrt(E)-weighted number moment equals `f_i*M_i`. A zero-valued donor
cannot create spurious electrons. Reference EEPFs must already be finite,
nonnegative and normalized; invalid input fails closed.

For each linear cross-section segment, integrate
`E * sigma(E) * [1+s_i(E-mu_i)]` **analytically in local coordinates**.
The same reconstructed integral is used for ionization donor loss,
equal-energy-sharing daughter gain into each destination cell,
attachment loss, and per-target rate diagnostics. The matrix
conservation audit verifies that the donor column sum is exactly
`ionization_events - attachment_events` within tolerance.

The legacy three-argument `assembleGrowthCollisions`, four-argument
`evaluateGrowthOnFrozenEepf` and four-argument
`solveElasticTemporalGrowth` calls retain the original piecewise-constant
behavior. Supplying an optional reference EEPF opts into a frozen
reconstructed growth operator. No production Physics/ICP code is changed.

A new experimental Picard driver first solves the legacy M6b eigenproblem,
then repeatedly reconstructs from the preceding eigenvector, rebuilds
the ionization/attachment Q, and **re-solves the actual M6b generalized
eigenproblem**. Each update checks the sqrt(E)-weighted FV L1 difference,
maximum per-process rate change, true generalized eigen residual, and
collision-number balance. Two stable updates are required by default.
Resource/iteration limits return explicit `HOLD_PICARD_MAX_UPDATES`
with last computed solution and complete history. A numerically converged
Picard fixed point has status
`CONVERGED_PICARD_GROWTH_ONLY_SCIENCE_HOLD`, not science PASS.

## Reproducible C++ synthetic evidence

`tests/boltzmann/reconstructed_growth_picard_test.C` constructs a
**manufactured** steep EEPF tail with a cell
`[15.71321743,15.8367]` eV and a synthetic cross section that turns on
linearly at `15.8` eV. It checks exact subcell integral against an
independent 100,000-subinterval midpoint quadrature (relative error
<1e-9), nonnegative edge values, exact electron-number mass,
equal-sharing source/gain ledger, attachment sink, and rate-Q agreement.

Actual GitHub C++ output:

```text
manufactured_threshold_ratio = 0.649606
reconstructed_mass = 1
collision_balance = 0
eigen_residual = 2.41255e-14
first_Picard_L1 = 6.31502e-06
nominal_Picard = CONVERGED_PICARD_GROWTH_ONLY_SCIENCE_HOLD
nominal_updates = 3
nominal_final_L1 = 2.1556e-14
nominal_final_rate_change = 6.62992e-12
strict_HOLD = PASS
```

The **0.649606** ratio is for invented `sigma(E)` and an invented
tail; it is **NOT** a measured correction of BOLSIG+ C3 +13.02% error.
The coupled 36-cell eigen test uses synthetic ionization, attachment
and excitation. Excitation remains on the legacy constant-cell
conservative operator. The deliberately permissive Picard-state test
is separate from the default numerical tolerance test; the strict
1e-14 one-update test explicitly returns HOLD.

## Remaining scientific gates

- Extend the same subcell reconstruction to the **excitation and
  superelastic conservative source/gain operator**; preserve detailed
  balance and energy-loss moments.
- Recompute the mean-energy moment using reconstructed f0(E), or prove
  and bound the constant-cell moment discrepancy; the current output
  still uses the original FV constant-cell mean-energy formula.
- Run strict independent Emax + mesh refinement together with Picard
  fixed-point convergence. Demonstrate stable rates, moments, EEPF and
  thresholds at 400–1000+ cells using a scalable eigensolver.
- Run the real Example 1–4 (151 conditions) BOLSIG+/LXCat comparisons
  with independently selected Emax. Retain native error -1 on Example 1
  high-field runs, the Example 2 R5 mobility ~10% discrepancy, the
  Example 4 C3 +13.02% original discrepancy and unresolved O2
  three-body attachment units until **new genuine evidence** exists.
- No main merge, no production Oxygen ICP closure modification, and
  no science approval while these gates remain open.

**Verdict:** P0-3 has an implemented, tested conservative
ionization/attachment reconstruction and real C++ iterative growth
eigen re-solve. It is **PARTIAL / SCIENCE HOLD**, not a completed
physics-wide reconstruction or BOLSIG+ parity claim.
