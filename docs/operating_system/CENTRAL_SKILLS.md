# Paul Central Operating Contracts

**Status:** canonical consumer manifest guide  
**OS:** Paul  
**Central revision:** `908d5b695b4640727b3c45d8044763c5fcca1d08`

The machine-readable exact identities are in `central_skills.json`.

## Initialization load

A successful `moose-test-init` loads from the same exact central revision:

```text
docs/operating_system/README.md
docs/operating_system/ESSENTIAL_RULES.md
skills/session-bootstrap/README.md
skills/state-refresh/README.md
```

The first two establish Paul OS/common-rule authority. The skills own generic bootstrap and refresh mechanics.

## Trigger-loaded contracts

Load only when triggered:

```text
MUTATE
  -> skills/repository-mutation/README.md

GOVERNED_WORK
  -> skills/governed-work/README.md

SCHEDULED_CONTROLLER
  -> skills/controller-throughput/README.md
  -> skills/controller-lifecycle/README.md
  -> state-refresh remains available
```

Do not preload controller skills during an ordinary interactive init.

## Verification

For every required central artifact:

1. use the exact repository/revision/path from the manifest;
2. verify the Git blob SHA;
3. read the contract before applying it;
4. never substitute floating `main` or a locally copied implementation.

If a required init artifact cannot be verified, initialization is incomplete and remains read-only.

A trigger-loaded artifact failure blocks only the affected operation.

## Ownership

Central Paul contracts own generic mechanics and essential cross-repository invariants.

This repository retains Physics scientific semantics, P0-P3 meaning, production runtime evidence, numerical acceptance, repository-specific dependency readiness, and local authorization.

Operating-process metrics are not part of the Paul initialization contract.
