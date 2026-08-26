# R4/R5 A6 production-oracle constant convention mismatch

**Status:** OPEN  
**Issue:** #13 `oxygen-heavy-transport-db`  
**Class:** validation-reference / production-parity constant convention

## Symptom

User-local `qpx-opt` R4/R5 canonical validation passed all source/data/resolver and mutation gates, while A6 production-path construction/runtime succeeded for every case but strict numeric parity failed:

```text
P0: PASS
A0_SCHEMA_STATIC: PASS
A1_SOURCE_PROVENANCE: PASS
A2_RAW_TO_SI: PASS
A3_EXHAUSTIVE_RESOLVER: PASS
A4_INTERPOLATION_RANGE: PASS
A5_PROVENANCE_PRECEDENCE: PASS
A7_VALIDATOR_MUTATION_SELFTEST: PASS

explicit_neutral_node     1.449e-06
explicit_neutral_offgrid  1.449e-06
explicit_ionneutral       1.447e-06
langevin_negative         1.447e-06
dynamic_attractive        3.029e-06
dynamic_repulsive         3.422e-06
dynamic_state_ne          3.972e-05

A6_QPX_PRODUCTION_PATH: FAIL
BATCH_A_FAIL
```

Every A6 `--check-input` and runtime return code was zero. The accepted R3 dynamic Debye-Huckel implementation had already passed independent end-to-end parity at `2.42e-08` to `4.54e-08`.

## H1 -> T1: production QPX implementation defect

**H1:** the R4/R5 production implementation or resolver is wrong.

**T1 evidence:**
- A0-A5 all pass;
- all 49 ordered physical resolver queries produce the intended explicit/Langevin/dynamic provenance;
- A7 detects all ten injected defects;
- every A6 construction and runtime call succeeds;
- the previously accepted R3 charged path passes an independent runtime oracle at < `5e-8`.

**Decision:** H1 REJECTED as the primary explanation for the observed A6 failure vector.

## H2 -> T2: CSV output precision

**H2:** numeric values are being rounded strongly enough by CSV output to create the observed parity errors.

**T2:** the corrected harness explicitly writes CSV with precision 17 and scientific notation, and the previous failure magnitudes vary systematically with transport class/state rather than with printed magnitude alone.

**Decision:** H2 REJECTED as the primary failure mechanism. The explicit precision setting remains as a regression hardening measure.

## H3 -> T3: upstream historical constants leaked into the production-parity oracle

The R4/R5 v1 independent oracle reused historical numerical constants from the pinned Mutation++ source model throughout the QPX production-parity calculation:

```text
k_B  = 1.3806503e-23
N_A  = 6.0221415e23
e    = 1.602176565e-19
eps0 = 1/(mu0*c0^2)
```

The accepted QPX/R3 production path instead uses the QPX numerical convention represented by:

```text
k_B  = 1.380649e-23
N_A  = 6.02214076e23
e    = 1.602176634e-19
eps0 = 8.8541878128e-12
R    = 8.31456 J/(mol K) for the host EOS conversion
```

A behavioral mutation test was built by taking the corrected production oracle and replacing only those QPX-side constants with the historical Mutation++ values. It predicts the external v1 failure vector:

```text
case                      predicted       observed
explicit_neutral_node     1.473817e-06    1.449e-06
explicit_neutral_offgrid  1.473817e-06    1.449e-06
explicit_ionneutral       1.472300e-06    1.447e-06
langevin_negative         1.472590e-06    1.447e-06
dynamic_attractive        3.054526e-06    3.029e-06
dynamic_repulsive         3.447733e-06    3.422e-06
dynamic_state_ne          3.972241e-05    3.972e-05
```

The residual predicted-vs-observed difference is ~`2.5e-8`, consistent with the already established independent-oracle residual scale from R3.

**Decision:** H3 SUPPORTED.

## Corrective action

1. Keep A1/A2 pinned to the Mutation++ source tables and source provenance. Those gates answer whether the upstream model/data were extracted and transformed correctly.
2. For A6, use an independent implementation of the equations but the numerical constants of the accepted QPX production convention. A6 answers whether QPX runtime reproduces its intended production model.
3. Keep the strict `2e-7` A6 threshold; do not loosen tolerance.
4. Add a behavioral oracle mutation self-test that reintroduces the historical constants and must reproduce/detect the v1 failure signature.
5. Supply electron state inputs only when both active aliases are charged, matching the production conditional contract.
6. Force CSV precision 17 and print per-observable `got/ref/rel` values for future diagnostics.

Corrected standalone bundle:

```text
oxygen_transport_R4_R5_canonical_validation_v2.tar.gz
SHA-256 9dd3604ff519ba345c6a5893ece1277ae13238c2c6285a1f12df130bbd110d78
```

Offline preflight of v2:

```text
MOOSE_STATIC_PREFLIGHT_SELFTEST: PASS
R4_R5_ORACLE_CONSTANT_SELFTEST: PASS
A0-A5: PASS
A7 M1-M10: all DETECTED
```

## Regression requirement

Run the v2 bundle with the accepted R3 v3 `QPXThermalDiffusionMaterial.C` and the rebuilt user-local `qpx-opt`. No production-source change is required for this incident.

Required closure signature:

```text
R4_R5_ORACLE_CONSTANT_SELFTEST: PASS
A0_SCHEMA_STATIC: PASS
A1_SOURCE_PROVENANCE: PASS
A2_RAW_TO_SI: PASS
A3_EXHAUSTIVE_RESOLVER: PASS
A4_INTERPOLATION_RANGE: PASS
A5_PROVENANCE_PRECEDENCE: PASS
A6_QPX_PRODUCTION_PATH: PASS
A7_VALIDATOR_MUTATION_SELFTEST: PASS
BATCH_A_PASS
```

Keep this incident OPEN until the corrected user-local A6 regression passes. Only then consider promoting the reusable lesson to the troubleshooting index.
