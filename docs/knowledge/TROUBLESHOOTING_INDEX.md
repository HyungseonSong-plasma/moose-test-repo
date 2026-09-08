# Troubleshooting Index

This index maps recurring symptoms to incident records and minimal regression cases.

| Symptom / keyword | First reference | Status |
|---|---|---|
| `DIVERGED_LINE_SEARCH` on repeated transient solve of algebraic FV potential | `docs/incidents/m5_ion_drift_failure_history.md` | residual-floor mechanism CLOSED for pure `phi` case |
| Solved-potential ion drift differs from prescribed-field reference | `docs/incidents/m5_ion_drift_failure_history.md` | investigation in progress |
| Wall migration postprocessor is nonzero but transient inventory does not include the same loss | `tests/m5_plasma_charge/ion_wall_migration_state/` | isolated diagnostic cases |
| Global nonlinear solve reports convergence after one field-dominated correction while a coupled species invariant is still wrong | `docs/incidents/m5_phi_ic_sweep_decision_matrix.md` | root cause confirmed; subsystem convergence evidence required |
| EOS identity appears to fail when `rho_avg` is approximated by `(rho_min + rho_max)/2` | `docs/incidents/step2_eos_validation_aggregation_error.md` | CLOSED; use matching spatial-average operators |
| Source classifier reports ambiguous because one exact C++ declaration spelling is absent | `docs/incidents/r3_source_contract_classifier_false_ambiguous.md` | CLOSED; classify semantic capability, not formatting token sequence |
| Independent oracle shows the same small multiplicative error for every physics state while state sensitivity still passes | `docs/incidents/r3_thermal_diffusion_gas_constant_scale_mismatch.md` | CLOSED; check host constant/unit convention before modifying production physics |
| Production-parity oracle fails by a transport-class-dependent but reproducible vector while source/provenance gates pass | `docs/incidents/r4_a6_production_oracle_constant_convention_mismatch.md` | CLOSED; separate upstream source constants from production numerical conventions |
| Validator expects `1e-14` but reparsed float is `1.0000000000000002e-14` | `docs/incidents/validator_representation_equivalence_false_fail.md` | CLOSED; use representation-aware equivalence and retain material negative control |
| Transient CSV has only `time=0` / INITIAL observation despite runtime return code zero | `docs/incidents/step3_csv_initial_only_output.md` | runtime-semantic evidence required before physics classification |
| Initial CSV row contaminates positivity/extrema acceptance | `docs/incidents/step3_initial_csv_zero_row_acceptance_error.md` | separate initialization and completed physical states |
| `--check-input` fails before runtime because generated test input omits state required by charged self-pairs or contains unsupported output knobs | `docs/incidents/r4_r5_a6_harness_construction_false_fail.md` | CLOSED; validate full active-set constructor contract |
| Duplicate shared material/functor producer appears only after subsystem composition | `docs/incidents/duplicate_shared_functor_provider_integration.md` | block-qualified provider ownership map required |
| `Invalid function ... Syntax error in parameter 'Vars' given to FunctionParser::Parse()` | `docs/incidents/functionparser_reserved_symbol_collision.md` | CLOSED; machine-enforced parser-symbol P0 added |
| `ADFParser::JITCompile() failed` while non-AD parsed path or later direct target behaves differently | `docs/incidents/adfparser_jitcompile_failure.md` | MONITORING; direct target evidence outranks supporting environment proxy |

## Reusable pattern: algebraic variable inside a transient solve

Observed pattern:

```text
Time Step n:
large initial residual -> tiny residual -> relative convergence PASS

Time Step n+1:
already-small initial residual -> numerical residual floor
-> absolute tolerance below floor
-> line-search failure
```

First diagnostic:

```text
compare nl_abs_tol with measured residual floor
```

Do not modify physics coefficients or timestep before checking this condition.

## Reusable pattern: validation aggregation mismatch

When checking an integral or average identity, do not replace a domain average with a midpoint of extrema.

Invalid example:

```text
rho_avg ~= 0.5 * (rho_min + rho_max)
```

Correct approach:

```text
compare avg(rho) against an expression formed with compatible spatial averaging and weighting
```

For the Step-2 O2/O EOS test, `Mn` was spatially uniform, so the correct identity was

```text
avg(rho) = avg(p) * Mn / (R*T)
```

The corrected regression produced `EOS_rel_error = 2.198e-14`.

## Reusable pattern: semantic identity / admissible equivalence

A recurring validator failure family has appeared under different surface symptoms:

```text
serialized float representation != decimal literal by exact equality
midpoint of extrema treated as a spatial average
one exact source-code token sequence treated as semantic capability
INITIAL observation treated as completed physical timestep
historical source constant treated as host-production numerical convention
```

These are one ontology class, not unrelated bugs. Before comparing two artifacts/values/states, identify:

```text
semantic object
representation
owner / provenance
state / time identity
required equivalence relation
```

Then choose the narrowest justified comparison from VAL-16. The comparison must be no stronger than the producing representation guarantees and no weaker than the scientific claim requires.

Exact equality is appropriate only when exact identity is both guaranteed and material. If a tolerance/equivalence relation is introduced, retain a negative mutation that proves a materially different value still fails.

## Reusable pattern: semantic capability vs source spelling

Static source inspection must answer a capability question rather than match one preferred formatting unless syntax itself is the invariant.

Example:

```text
BAD: require exact text "std::vector<Real> Q11"
GOOD: prove collision-table schema + Q11 use + T-driven interpolation semantics
```

Formatting/layout changes must not alter a semantic source-contract classification.

## Reusable pattern: independent-oracle convention mismatch

If an independent oracle differs from production by nearly the same multiplicative factor across unrelated states, while the intended state sensitivities and branch discriminators remain correct, treat a downstream constant/unit/convention mismatch as a primary hypothesis.

Recommended discriminator:

```text
1. Compare a dimensionless/intermediate observable that does not contain the suspect conversion.
2. Compare the final dimensional observable.
3. Infer the effective scale/constant from production output.
4. Mutation-test the oracle convention before changing production physics.
```

The R3 thermal-diffusion case preserved `kT`, `Te` sensitivity, `ne` sensitivity, and Coulomb-branch sensitivity, while only final `D_T` carried a uniform ~`1.17e-5` offset. The cause was the oracle using modern exact `k_B*N_A` while QPX used its established host EOS `R` convention.

## Reusable pattern: source provenance vs production numerical contract

A source/provenance gate and a production-parity gate answer different questions. Keep source-data checks pinned to the upstream model, but let a production-parity oracle use the production implementation's declared numerical constants while remaining algorithmically independent.

If replacing production constants with historical upstream constants reproduces the external failure vector, classify the defect as an oracle-contract mismatch rather than a production-physics failure.

## Reusable pattern: active-set constructor validation

A targeted pair test may still trigger constructor checks for self-pairs and other pairs in the active species set. Generate inputs from the full constructor contract, not only the cross-pair being observed.

For charged-heavy transport, one charged species is enough to create a charged self-pair during `i <= j` validation, so `Te/ne` may be required even for an ion-neutral target cross-pair. Unsupported input parameters are harness failures; do not mask them with `--allow-unused`.

## Reusable pattern: FunctionParser variable namespace

For `ParsedFunctorMaterial` / `ADParsedFunctorMaterial`, a mathematically valid expression can still fail before evaluation if its parser-symbol namespace is invalid.

MOOSE appends coordinate/time symbols `x,y,z,t` and provides parser constants `pi,e`. Do not reuse those names as custom `functor_symbols`; also reject duplicate aliases and implicit `functor_names` collisions when `functor_symbols` is omitted.

Required first action for

```text
Syntax error in parameter 'Vars' given to FunctionParser::Parse()
```

is:

```text
python3 scripts/qpx.py preflight <input.i>
```

Do not change physics or solver settings before this namespace check.

## Ontology audit of recurring incident families

The incident archive was reviewed against CORE-16 to decide whether recurring logs require new ontology axes or are new symptoms of existing ones.

| Failure semantics | Representative evidence | Canonical owner | Audit decision |
|---|---|---|---|
| Failure stage / causal boundary | parser/JIT/P2 failures falsely tempting physics changes | CORE-07, VAL-01, VAL-18/19 | already represented; no new axis |
| Semantic identity / admissible equivalence | float exact comparison, aggregation mismatch, source-token classifier, source/host convention, INITIAL-row identity | CORE-16, VAL-16 | **generalized/promoted** |
| State / observation timing | INITIAL CSV rows, old/current state, wall flux vs timestep-end diagnostics | VAL-15, VAL-17, VAL-20 | already represented; strengthen via semantic identity |
| Namespace / provider ownership | reserved parser symbols, duplicate `T_g` provider | VAL-03, VAL-19 | already represented; no new axis |
| Effective environment/framework identity | AD FParser JIT environment and MOOSE default time controls | VAL-06, VAL-18, VAL-21 | already represented; no new axis |
| Solver termination semantics | residual floor; global convergence hides species residual | PS-08, CORE-16 evidence sufficiency | already represented; solver PASS is not scientific PASS |
| Provenance / convention separation | R3/R4 source vs host-production constants | VAL-10-12, VAL-16 | already represented; no new axis |
| Numerical/coupling regime conformance | sub-picosecond `dtmin`/tolerance conflict; fast/slow coupling | PS-23, VAL-21 | already represented; no new axis |
| Repository action intent preservation | wrong mutator/resource/phase/verification actions | `docs/protocols/repository_mutation.md` | parallel **operational ontology** already implemented; keep separate from scientific CORE-16 |

The audit result is intentionally conservative: do not create one ontology class per error message. Different symptoms belong to one ontology class when the same semantic contract was violated.

## Future incident ontology audit

For every new material incident, after preserving the raw chronology/root-cause evidence, ask:

```text
1. What was the earliest execution/operation stage actually reached?
2. What semantic object was the claim about, and who owned it?
3. What representation was observed or compared?
4. What equivalence relation did the validator assume?
5. Which state/time/regime did the observation actually represent?
6. Was the evidence direct target evidence or only a proxy/supporting diagnostic?
7. Which CORE-16 / protocol link failed first?
8. Is this a genuinely new ontology class, or only a new symptom of an existing class?
```

Promote a new ontology/rule only for a materially distinct semantic failure that cannot be expressed by an existing owner without mixing responsibilities. Otherwise improve the existing trigger, checker, or machine-enforced guard.

## Incident promotion rule

An incident can be promoted from `docs/incidents/` to reusable knowledge only after:

1. root cause is isolated,
2. fix is verified,
3. regression gate passes,
4. scope/limitations are documented,
5. the incident has been mapped to the broken ontology/protocol link and checked for reuse versus genuine novelty.
