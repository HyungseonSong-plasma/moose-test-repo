# MOOSE/Physics Cross-Chat Bootstrap

**Status:** canonical consumer entry point  
**Command:** `moose-test-init`  
**OS:** Samuel

## Contract

Generic initialization mechanics are owned by the exact pinned Samuel `session-bootstrap` skill.

This file supplies MOOSE/Physics-specific sources, routing inputs, and report additions.

## Bootstrap sequence

```text
1. read docs/operating_system/README.md;
2. read central_skills.json + CENTRAL_SKILLS.md;
3. verify the exact central revision and OS = Samuel;
4. verify/read central ESSENTIAL_RULES.md;
5. load session-bootstrap + state-refresh from that same revision;
6. verify/read pinned skills/catalog.json and skills/capability-registry.json, and record capability routing readiness independently from visible tools;
7. read OPERATING_CORE.md;
8. recover the active issue/bounded-work STATE and immediate obligation;
9. read PROTOCOL_INDEX.md and docs/protocols/rule_working_set.md;
10. select one local primary semantic phase;
11. load only its local owner(s) plus immediately triggered Samuel skills/capabilities/diagnostic evidence; if GitHub mutation or negative capability claim is involved, resolve the owning skill AND registry-ordered providers;
12. report restored state, GitHub capability-routing status, first real gate, and uncertainty;
13. stop read-only.
```

Initialization is incomplete if required Samuel authority or required init contracts cannot be verified.

## GitHub capability bootstrap gate (required, read-only)

Before reporting `moose-test-init` complete, read and verify the **pinned** `skills/catalog.json` and `skills/capability-registry.json` identified by `docs/operating_system/central_skills.json`. Keep the verified exact revision and trigger/provider mapping in the operating context, not as a conclusion inferred from a connected GitHub tool.

```text
GITHUB_CAPABILITY_ROUTING=READY|BLOCKED
GITHUB_MUTATION_PREFLIGHT=TRIGGER_REQUIRED
```

`READY` means the catalog and registry were actually read and verified; it does **not** authorize mutation or assert that an execution provider is currently accessible. If either source is missing or unverified, report `BLOCKED`, stop the affected action, and do not claim that Samuel lacks the capability. Initialization itself remains read-only.

For **every** GitHub state-changing operation, even after successful init and even after a context reset: resolve the owning Samuel trigger in the verified catalog, load its central skill, resolve ordered providers from the verified capability registry, and refresh target identity/permissions before choosing the provider. Rehydrate this routing after any context loss rather than relying on chat memory. A connector's visibility does not grant an exception.

If a connector lacks a particular operation, that is only provider-local evidence. Before claiming any GitHub mutation is globally unavailable, trigger `GITHUB_MUTATION_CAPABILITY_VERDICT` / `repository-mutation` and satisfy registry exhaustion using `assert_capability_exhausted` where required. Do not invent alternate workflows or redirect the user to manual changes until the registered native provider has been evaluated.

Example: `GITHUB_BRANCH_DELETE` resolves to Samuel's `repository-native` exact-SHA `github-branch-delete` contract before its connector fallback. The consumer already has `.github/workflows/samuel-branch-delete.yml`, triggered by `automation/mutations/branch-delete-request.json`; verify this current route instead of assuming deletion is unavailable. Never delete during initialization.


## Scheduled-controller continuation

An ordinary interactive init does not preload controller execution paths.

When a scheduled-controller trigger is active, load from the same exact central revision:

```text
state-refresh
controller-throughput
controller-lifecycle
```

When the immediate obligation requires the durable generic controller, trigger `research-controller`; when it requires PR merge, trigger `pull-request-merge` / `GITHUB_PR_MERGE` and use Samuel capability routing.

Continue from a durable controller checkpoint and apply central state-refresh semantics. Physics dependency readiness and scientific gates remain local.

## Minimum report

Report:

```text
OS = Samuel
exact central revision
essential rules loaded
init skills loaded
capability registry verified
GITHUB_CAPABILITY_ROUTING=READY|BLOCKED
GITHUB_MUTATION_PREFLIGHT=TRIGGER_REQUIRED
repository / ref
active work item / immediate obligation
primary local phase
triggered central skills/capabilities
first real gate / blocker
evidence uncertainty
```

No operating-process metrics context is required.

## Historical metrics

Calvin-era operating metrics are archived at `archive/operating_metrics/` and must not be loaded by initialization.

Scientific/runtime/numerical/performance evidence required by the owning Physics claim remains live under its technical protocol.
