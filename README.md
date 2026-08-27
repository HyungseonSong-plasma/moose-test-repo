# MOOSE/QPX Test Workspace

This repository is the operating and regression workspace for MOOSE/QPX plasma-simulation development.

## Operating boundary

Use `OPERATING_CORE.md` for always-active rules and `PROTOCOL_INDEX.md` for deterministic procedure routing. Current technical state is owned by the active GitHub issue body; issue comments are historical evidence.

## Current development sequence

```text
#19 CLOSED/PASS
  -> #21 CLOSED/PASS
  -> #22 CLOSED/PASS
  -> #15 CLOSED/PASS
  -> #24 CLOSED/PASS
  -> #2 CLOSED/PASS
  -> #16 ACTIVE
  -> #17 BLOCKED
```

Current target: #16 heavy + electron charge-density construction and self-consistent Poisson coupling, consuming the accepted heavy-species and electron drift-diffusion contracts without reimplementation.

## Validation model

Runtime canonical evidence comes from the user-local real `qpx-opt`. GitHub Actions and static checks are supporting evidence. Technical validation follows P0 -> P1 -> P2 -> P3 and the bounded EVR workflow defined in the protocol documents.

## Repository role

This workspace stores regression inputs, minimal reproducers, checkers/reference data, incident/development logs, scripts, and small source deltas needed to reproduce or document MOOSE/QPX investigations. Production source changes belong in the appropriate source repository.