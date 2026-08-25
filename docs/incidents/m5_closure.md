# M5 Solved-Potential Ion Wall Migration — Closure Record

**Status:** CLOSED  
**Work ID:** `M5-ion-wall`  
**Scope:** solved-FV-potential-driven O2+ bulk drift, surface wall loss, and migration wall loss

## Closure criteria

M5 is formally closed because all required conditions have been satisfied:

1. root cause identified with independent evidence;
2. production convergence strategy selected;
3. full-coupled regime validation passed;
4. zero-initial-potential wall-only regression promoted to canonical;
5. zero-initial-potential full-coupled regression added as canonical;
6. canonical promotion validation executed in the working QPX runtime and reported PASS.

Final promotion result:

```text
M5 CANONICAL PROMOTION VALIDATION: PASS
```

## Root cause

The wall-migration physics was not defective.

The failure mechanism was **premature global nonlinear convergence** in the coupled electrostatic/species solve. The dominant electrostatic residual and automatic-scaling/global-norm interaction allowed the first Newton correction to satisfy the global relative convergence criterion while the smaller O2+ species-wall coupling still required another nonlinear correction.

The zero-field hard migration gate produced a distinctive first-iteration branch, but it was not the dominant root cause.

Evidence included:

- bulk exact/zero solved-potential drift cases PASS;
- wall exact PASS and zero-IC wall failure under the original convergence rule;
- initial-potential sweep matching the analytic one-Newton signature;
- `nl_forced_its=2` restoring conservation;
- tight relative tolerance independently restoring the same conservative state;
- production convergence screening showing species-aware reference residual convergence restores conservation without extra nonlinear cost;
- full-coupled finalist validation passing across initial-potential, timestep, and mobility variations.

## Production decision

Use:

```text
global convergence
AND
species-aware ReferenceResidualConvergence
```

for the charged-heavy-species convergence gate while retaining automatic scaling.

Manual explicit scaling with `automatic_scaling=false` remains a diagnostic/fallback control, not the production default.

Do not modify mixture-averaged diffusion, `QPXFVElectrostaticDrift`, or `QPXIonWallFluxMaterial` physics to address this closed incident.

## Canonical promotion

Permanent regressions now include the zero-initial-potential cases required to prevent recurrence:

- `wall_only_zero_phi_ic` — canonical;
- `full_zero_phi_ic` — canonical.

The mass-balance gate remains `1e-8` or tighter.

## Hold-point release

The M5-specific hold point is released. Work may proceed to later MOOSE-team layers, including:

- reactor-scale O2+ integration;
- electron bulk drift;
- ion/electron dielectric surface-current accumulation;
- secondary electron emission;

Each layer remains subject to its own canonical and diagnostic gates.

## Validator baseline

M5 is the first Work Closure Validator baseline.

Because Validator instrumentation was introduced late in this incident, complete historical chat-round boundaries are not available. Therefore WCC/T-WCC are recorded as conservative lower bounds, not invented exact counts.

Reconstructed metrics:

```text
Complexity: C3
WCC:       >=20   (lower bound; pre-validator history incomplete)
T-WCC:     >=15   (lower bound)
EVR:       8
DBR:       5
RWR:       2
CLR:       0 known
FBR:       no
Reopened:  no
```

### EVR reconstruction

The eight identifiable user-executed result-return rounds were:

1. canonical + 2x2 solved-potential localization matrix;
2. smooth-gate diagnostic;
3. forced-nonlinear-iteration diagnostic;
4. initial-potential amplitude sweep;
5. quantitative convergence probe;
6. production convergence screening batch;
7. full-coupled finalist validation batch;
8. canonical promotion validation.

### DBR reconstruction

Root cause required five external diagnostic batches before production-fix validation began:

1. localization matrix;
2. smooth-gate test;
3. forced-iteration test;
4. IC-amplitude sweep;
5. convergence probe.

`FBR = no` because the root-cause class was not resolved in the first batch.

### RWR reconstruction

Two avoidable interaction rounds are counted:

1. a test runner interpreted the QPX executable path after changing working directory, requiring a corrected bundle using `realpath`;
2. an early forced-iteration diagnostic reported process PASS/FAIL without the required numeric conservation invariant, which contributed to an incorrect interim interpretation and required a quantitative follow-up probe.

## Process lesson

The main efficiency lesson is:

> Generate the plausible hypothesis set up front and execute a high-information parallel diagnostic batch that includes convergence sensitivity and numeric invariants before source modification or framework-deep inspection.

For similar C3 coupled incidents, the target is now:

```text
RWR = 0
DBR <= 2
EVR <= 2 before root-cause/production-validation transition
```

This closure record supersedes any earlier `Investigation in progress`, `Current hypothesis`, or M5 hold-point wording in chronological incident-history documents; those sections remain historical evidence only.
