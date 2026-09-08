# WB5 performance orchestration — acceptance scope

Parent: #154
Performance child: #155

This batch normalizes performance orchestration only. It does not optimize performance and does not change plasma physics, numerical algorithms, solver tolerances, timesteps, or accepted scientific states.

## Ownership after WB5

```text
CLI
  -> application.performance
       -> adapters/moose/performance   # MOOSE raw syntax/decoding
       -> adapters/petsc/performance   # PETSc raw syntax/decoding
       -> execution.runtime            # backend-neutral process mechanics
       -> analysis.performance         # decoded facts -> interpretation
```

The mixed-owner `execution/performance` package is retired. PF-3 transport campaign probes are removed from production adapter ownership; historical Git provenance remains available.

## Intended checks

- one CLI-facing performance application entry surface;
- no raw external decoder import from generic analysis;
- no MOOSE/PETSc raw syntax owner in generic execution;
- no broken `execution/performance/probes` namespace;
- no retired `execution.performance.runner` / `profiling` production owner;
- dependency/cycle/architecture guards;
- QPX-free pytest;
- canonical `python qpx -i all` only when actually executed by CI;
- `SCIENTIFIC_EVR_CONSUMED = 0`.
