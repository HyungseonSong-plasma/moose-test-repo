# MOOSE/Physics Operating System Binding

**Status:** Samuel consumer binding  
**Consumer:** `HyungseonSong-plasma/moose-test-repo`  
**Canonical OS repository:** `HyungseonSong-plasma/chatgpt-operation`  
**Pinned central revision:** `20827ec81ab0eac4dd7560a22ee4212e274113a5`  
**Expected OS:** Samuel

## Central authority

Resolve exactly:

```text
repository          = HyungseonSong-plasma/chatgpt-operation
revision            = 20827ec81ab0eac4dd7560a22ee4212e274113a5
OS index            = docs/operating_system/README.md
essential rules     = docs/operating_system/ESSENTIAL_RULES.md
session bootstrap   = skills/session-bootstrap/README.md
skill catalog       = skills/catalog.json
capability registry = skills/capability-registry.json
```

Exact artifact identities and adopted load triggers are in:

```text
docs/operating_system/central_skills.json
docs/operating_system/CENTRAL_SKILLS.md
```

Do not substitute a floating central ref or mix central revisions inside one operating decision cycle.

## Local authority retained here

This repository remains authoritative for:

```text
Physics scientific semantics
production runtime evidence meaning
P0/P1/P2/P3 validation meaning
model/regime acceptance
repository dependency readiness
issue/milestone acceptance
local role/mode semantics
current durable work STATE
```

Central Samuel rules/skills/controller mechanics do not establish scientific PASS or redefine Physics meaning.

## Initialization

`moose-test-init` must:

```text
1. verify this exact Samuel binding;
2. verify/read the Samuel OS index and ESSENTIAL_RULES;
3. load session-bootstrap + state-refresh + problem-oriented-response (README and contract.json) from the same revision;
4. verify/read skills/catalog.json and skills/capability-registry.json from the exact pinned revision; report GITHUB_CAPABILITY_ROUTING=READY|BLOCKED independently from provider visibility;
5. restore the Physics-local operating core and current STATE;
6. resolve immediate-obligation trigger(s) and load matching central skill plus registry-ordered providers, including GITHUB_BRANCH_DELETE and GITHUB_MUTATION_CAPABILITY_VERDICT when triggered;
7. report OS = Samuel, exact revision, restored state, GITHUB_MUTATION_PREFLIGHT=TRIGGER_REQUIRED and the first real gate;
8. stop read-only.
```

Initialization does not itself authorize mutation, workflow execution, merge, or semantic acceptance.

After init, any GitHub state-changing request re-enters **Samuel trigger → skill → capability registry → ordered providers → fresh evidence → mutation → read-back**. Rehydrate after context loss. A missing connector operation is not global capability exhaustion; evaluate only the registered providers and central negative-verdict guard.

For `GITHUB_BRANCH_CREATE`, `GITHUB_FILE_CREATE`, `GITHUB_PR_CREATE`, and `GITHUB_COMMENT_CREATE`, resolve the single `github-connector` provider from the pinned registry, discover its live action schema, check current target identity and authorization, execute, and read back. No native fallback for these four. Other capabilities retain their registered provider order. Hard denials stop the affected operation; do not bypass them.

The required branch preflight policy path `automation/samuel/repository-mutation-policy.json` is an exact JSON mirror of `.chatgpt-operation.json`, not independent authorization. Repository CI rejects drift.

## Samuel controller continuation

Scheduled/durable controller work uses the same exact central revision. Generic action lifecycle, checkpoint/resume, trusted validation, native GitHub execution, and deterministic recovery are Samuel-owned mechanics.

Physics dependency readiness and scientific/domain acceptance remain local.

## Historical operating metrics

The former Calvin operating metrics and metrics-closure protocol are archived under:

```text
archive/operating_metrics/
```

They are historical evidence only and are not live Samuel routing, initialization, acceptance, or rule-quality authority.

Scientific/runtime/performance metrics used by Physics validation are unaffected.
