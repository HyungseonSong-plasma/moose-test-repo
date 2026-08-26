# INC-R3-CONTRACT-001 — R3 source-contract classifier false ambiguous

**Status:** CLOSED  
**Parent work:** #13 `oxygen-heavy-transport-db`  
**Class:** validation harness / static source classifier

## Symptom

The R3 architecture probe reported:

```text
has_static_T_Q_tables=False
has_dynamic_electron_density_input=False
has_dynamic_electron_temperature_input=False
has_Debye_Huckel_runtime_model=False
evaluate_signature_T_p_Y_only=True
fixed_Bstar_Cstar_database_model=True
dynamic_screening_ready=False
static_only=False
R3_SOURCE_CONTRACT_AMBIGUOUS
```

This produced `R3_PROBE_FAIL` even though the source was in fact a temperature-table implementation with no dynamic Debye-screening state.

## Root cause

The classifier used an exact textual sentinel for table declarations:

```text
std::vector<Real> T
std::vector<Real> Q11
std::vector<Real> Q22
```

The actual `QPXThermalDiffusionMaterial` declaration is split across the header/source and is semantically represented by `CollisionTable`, `current_table.T/Q11/Q22.push_back(...)`, and runtime calls `interpolateCollisionIntegral(T, table.T, table.Q11/Q22)`.

Therefore a formatting/layout difference was incorrectly interpreted as missing table capability.

## Fix

Classify source contracts by **semantic capability**, not one exact C++ spelling.

The corrected classifier requires evidence for:

- collision-table schema/use;
- `evaluate(T,p,Y)` path;
- `Q11/Q22` lookup driven only by heavy-species `T`;
- pair `B*` / `C*` read from the static database;
- absence of dynamic electron-temperature/electron-density functor inputs;
- absence of a runtime Debye-Huckel evaluator.

It separately recognizes a dynamic-screening implementation only when `Te`, `ne`, and Debye-Huckel runtime capability are all present.

## Verification

Regression self-tests cover:

1. current-QPX-shaped static table semantics -> `static_only=true`;
2. dynamic `Te/ne` + Debye-Huckel semantics -> `dynamic_screening_ready=true`;
3. genuinely incomplete source -> ambiguous;
4. declaration/formatting mutation -> classification unchanged.

The corrected R3 probe regression produces:

```text
SOURCE_CONTRACT_CLASSIFIER: PASS
has_collision_table_schema=True
has_dynamic_electron_density_input=False
has_dynamic_electron_temperature_input=False
has_Debye_Huckel_runtime_model=False
evaluate_signature_T_p_Y_only=True
T_only_collision_integral_lookup=True
fixed_Bstar_Cstar_database_model=True
static_only=True
R3_ARCHITECTURE_CHANGE_REQUIRED
```

## Reusable rule

Static source-analysis validators must test **behavioral/semantic contracts** rather than require one source-code token sequence. Exact textual sentinels are acceptable only when the exact syntax itself is the invariant being validated.
