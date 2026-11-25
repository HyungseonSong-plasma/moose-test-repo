# Repository Integration Contract Verification — v0.1

**Owner:** `.github/workflows/ci.yml` (generated verbatim from
`ci/workflow_templates/general-ci.yml`).

## Definition

Repository CI is the **mandatory exact-Git-HEAD integration-contract gate**.
It verifies that a proposed change respects shared repository contracts:
Workflow routing and event surfaces, source dependency direction, architecture
and cross-repository interfaces, automation control-plane compatibility, and
the consistency of required integration evidence.

Repository CI does **not** establish physics-model validity, execute P3/P4
scientific acceptance, or prove runtime/semantic compatibility. It does not
need to run all historical experiment tests on every change.

## Allowed core gate

The only Repository CI Job is `validate`, without a job-level skip condition.
It runs on `main` push and every PR opened/synchronize/reopened/edited event,
without path filtering. Mandatory steps verify:

- Exact checkout HEAD and static Workflow generator/output parity
- Governed Workflow surface and ownership contract, including mutation tests
- Repository control-plane and skill integration contracts
- Declarative experiment gateway, dependency direction and canonical cycles
- Physics/SOL boundary, architecture census and active-CI residue

A changed or unfamiliar directory **cannot disable** the core gate through
path filters. A success conclusion is valid only when `validate` ran and
completed successfully. A skipped required gate is **HOLD**, not PASS.

## Specialized CI (not part of Repository CI)

| Owner | Source scope | Responsibilities |
| --- | --- | --- |
| `physics-code-ci.yml` | Physics, tests, experiments, domain guards/templates | Physics Python tests, static physics rules, retired Factory archive and consumer invariants |
| `physics-native-ci.yml` | Native Physics source, Native scenarios, selected related guards | CORE/ARCH Native P1/P2, runtime smoke, Boltzmann C++ controls |
| `physics-p6-validation.yml` | Manual only | Same W1 and both New-only 42/100-row P2 lanes |
| `plasma-native-regression.yml` | Manual only | Existing broad Plasma Native regression and legacy HOLD evidence |
| `harness-code.yml` | `physics_harness/code/**` | Harness Code unit/negative controls |
| `repository-diagnostics.yml` | Manual `workflow_dispatch` only | Historical one-day Artifact CreateArtifact API probe |
| Existing scientific Workflows | Explicitly authorized input/trigger | Scientific P3/P4 and special-run evidence |

The `physics-native-ci.yml` path filter is intentionally restricted to
Native-relevant changes. In particular, a Harness Code-only PR is **not**
automatically a native rebuild. When influence outside these paths is newly
discovered, extend its routing surface before declaring it out of scope.

These independent domain workflows retain their acceptance requirements.
**Repository CI PASS does not replace a failed or omitted applicable domain
check.** Required status-check/ruleset enforcement for specialized workflows
must be reviewed separately; do not infer branch-protection semantics from
GitHub's overall Workflow conclusion.

## Exact validation inventory and retirement evidence

The machine-readable contract
[`ci/contracts/repository_ci_scope_v1.json`](contracts/repository_ci_scope_v1.json)
enumerates all 17 original jobs and all 50 `validate` steps with their new
owners. `ci/guards/repository_ci_scope.py` fails on an extra/missing Job,
changed core or Physics Code step ownership, missing native path coverage,
or a conditional/skipped required `validate`.

Migration intent: **move existing checks, not silently delete them**. Existing
source-mutation negative tests, exact-HEAD identity, pinned OCI, P1/P2 evidence
and uploads remain in their respective domain Workflows. The artifact API probe
is a manual infrastructure diagnostic and never a global merge gate.

## Verdict model

- **PASS:** all required core checks executed and passed for the exact HEAD.
- **FAIL:** a verified contract violation or failed mandatory core check.
- **HOLD:** missing, skipped or unverified required evidence; no successful
  conclusion may be inferred.
- **N/A:** only for an individually scoped domain check with a declared,
  evidence-supported non-applicability reason; not a global verdict.

Domain CI may require further checks for a specific change. Runtime scientific
claims remain bound to separately approved Physics validation contracts.

Related issue: #749.

## Manual Native qualification

P6 and Plasma Native Regression are separate manual workflows, not automatic PR checks. Select the exact same-repository branch, enter its 40-character HEAD SHA, the open PR number (empty only for main), and `NATIVE_VALIDATION_APPROVED`. Main or an open internal PR into main must match the live source identity. Execute relevant manual checks before accepting changes affecting their Physics/Native contracts; unrelated changes may record explicit N/A, not PASS. A skipped/unrun manual check is never evidence of native or scientific success. Preserve existing OCI, W1 custody, protected-data cleanup, negative controls, and SCIENCE_HOLD. Server-side required checks and independent review must be reconciled before rollout; do not silently weaken branch protection.
