# Samuel Central Operating Contracts

**Status:** canonical consumer manifest guide  
**OS:** Samuel  
**Central revision:** `125bae0358da93edd6726b013ebc4639ed2cff77`

The machine-readable exact identities are in `central_skills.json`.

## Initialization load

A successful `moose-test-init` loads/verifies from the same exact central revision:

```text
docs/operating_system/README.md
docs/operating_system/ESSENTIAL_RULES.md
skills/session-bootstrap/README.md
skills/state-refresh/README.md
skills/catalog.json              # trigger metadata index
skills/capability-registry.json  # capability provider metadata
```

The first two establish Samuel OS/common-rule authority. `session-bootstrap` and `state-refresh` own generic bootstrap/refresh mechanics. Catalog and capability metadata are indexed during init, but mutation/controller execution is not activated merely by indexing them.

## Trigger-loaded contracts

Load only when triggered:

```text
MUTATE
  -> skills/repository-mutation/README.md

GITHUB_BRANCH_DELETE
  -> skills/repository-mutation/README.md
  -> resolve GITHUB_BRANCH_DELETE through skills/capability-registry.json
  -> repository-native exact-SHA deletion is authoritative before connector fallback

GOVERNED_WORK
  -> skills/governed-work/README.md

SCHEDULED_CONTROLLER
  -> skills/controller-throughput/README.md
  -> skills/controller-lifecycle/README.md
  -> state-refresh remains available

RESEARCH_CONTROLLER
  -> skills/research-controller/README.md

GITHUB_ACTIONS_EXECUTION
  -> skills/github-actions-execution/README.md

GITHUB_ACTIONS_OBSERVATION
  -> skills/github-actions-observation/README.md

GITHUB_PR_MERGE
  -> skills/pull-request-merge/README.md
  -> resolve providers through skills/capability-registry.json

ARTIFACT_STAGING
  -> skills/artifact-staging/README.md

SCIENTIFIC_DISCRIMINATOR_CONTROLLER
  -> skills/scientific-discriminator-controller/README.md
```

Do not preload controller execution paths during an ordinary interactive init.

For GitHub state-changing work, provider visibility never bypasses the owning Samuel trigger/skill/capability resolution. A provider-specific missing operation is not a capability verdict until the registered provider chain is exhausted.

## Samuel controller authority

When triggered, Samuel central mechanics own generic durable execution behavior including:

```text
typed action lifecycle
durable checkpoint/resume
trusted exact-head validation
read-before/write/read-after GitHub mutation
postcondition verification
registered capability fallback
rejected-merge recovery
diagnostic/corrective recovery
```

These mechanics do not own Physics scientific meaning or acceptance.

## Verification

For every required central artifact:

1. use the exact repository/revision/path from the manifest;
2. verify the Git blob SHA;
3. read the contract before applying it;
4. never substitute floating `main` or a locally copied implementation.

If a required init artifact cannot be verified, initialization is incomplete and remains read-only.

A trigger-loaded artifact/capability failure blocks only the affected operation.

## Ownership

Central Samuel contracts own generic mechanics and essential cross-repository invariants.

This repository retains Physics scientific semantics, P0-P3 meaning, production runtime evidence, numerical acceptance, repository-specific dependency readiness, and local authorization.

Operating-process metrics are not part of the Samuel initialization contract.
