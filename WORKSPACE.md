# Workspace Operating Boundary

This repository is reserved for MOOSE/QPX development, regression, verification, and troubleshooting work.

Canonical operating rules are not duplicated here. Use:

- `OPERATING_CORE.md` — always-active invariants and authorization semantics;
- `PROTOCOL_INDEX.md` — deterministic routing to the minimum required procedure set;
- `docs/protocols/problem_solving.md` — bounded problem solving and 3-EVR workflow;
- `docs/protocols/validation.md` — P0-P3, checker/analyzer, production-path and data validation;
- `docs/protocols/metrics_closure.md` — WCC/RVR/EVR and closure accounting;
- `docs/knowledge/TROUBLESHOOTING_INDEX.md` — reusable symptom-specific knowledge.

Repository content may include MOOSE/QPX regression inputs, minimal reproducers, checkers/reference data, incident/development logs, scripts, and compatible local test executables.

Production source changes belong in the appropriate source repository. This workspace primarily stores test/development evidence and small source deltas only when needed to reproduce or document an investigation.

For current work state, use the active GitHub issue body. Issue comments are chronological evidence, not canonical current state.