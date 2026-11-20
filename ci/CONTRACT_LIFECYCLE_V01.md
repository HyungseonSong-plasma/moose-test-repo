# Contract Lifecycle v0.1 — Static invariants and temporary Dynamic gates

Authority: issue #754 (user clarification, 2026-11-20).
This classification is a **lifetime/authority decision**, not a technique for
automatic code discovery, path-filtered CI, or data-driven policy generation.
Inventory reflects PR #753 candidate HEAD and requires scoped acceptance before
any further Job/Guard deletion.

## Definitions

### STATIC — unconditional normative invariants

A Static Contract is a repository principle that must hold **regardless of the
development task, Issue, PR, experiment or migration**. It has no task-related
expiry. Implementation can optimize which tests run, but it must not weaken
the invariant or infer PASS from skipped required verification.

Candidates that meet the lifetime test:

- Exact source HEAD identity and provenance for all accepted verification.
- Repository workflows may run only authorized events/permissions; mandatory
  Repository CI cannot be silently bypassed.
- Required evidence cannot be fabricated, missing mandatory verification is
  not PASS, and status scopes cannot be widened without proof.
- P3/P4 scientific runs/acceptance require explicitly authorized scientific
  authority; a P0/P1/P2 check cannot claim higher-level acceptance.
- Dependency direction, integration boundaries and public contract
  compatibility **to the extent that they are approved permanent repository
  architecture** (independent of an Issue identifier).

**Static Contract ≠ static JSON file.** A JSON/YAML inventory of historical
Job names can encode TEMPORARY contracts and is not automatically a permanent
policy merely because its bytes are checked in.

### DYNAMIC — temporary acceptance contracts for a specific task

A Dynamic Contract exists only to develop or safely change a particular
capability. It must include:

`task_id / owner / scope / required_verification / evidence / acceptance_gate
/ retirement_gate / cleanup_refs`.

Lifecycle: `PROPOSED → ACTIVE → VERIFIED → ACCEPTED → RETIRED`.
At missing evidence, unresolved authority, unknown external consumers or
failed verification: `HOLD` (no automatic retirement).

- **VERIFIED is not ACCEPTED.** Passing CI does not approve code retirement,
  science or removal of historical support.
- **Retirement is actual cleanup**, not simply changing the trigger from
  `pull_request` to `workflow_dispatch`. Remove task-specific contracts,
  one-off Guards, special Job wiring, redundant contract entries and obsolete
  templates after acceptance; keep relevant history.
- A truly reusable invariant may be rewritten and approved as STATIC, and
  useful behavior regressions may be moved to a maintained test suite. Then
  retire the original Issue-specific contract. Do not quietly promote the
  entire one-off ledger as STATIC.

### Other objects, not additional contract lifetimes

- **REGRESSION TEST**: Maintained test of functionality, correctness or
  interoperability. It can remain after a Dynamic Contract is retired without
  itself becoming a permanent *contract*. Test routing is an efficiency choice.
- **HISTORICAL EVIDENCE**: Immutable source SHA, run/job/artifact ID, ZIP
  checksum, accepted receipt and prior results. Archive/read on demand; do not
  repeatedly verify unchanged historical facts as a general merge gate.
- **AUDIT TOOL**: Query/diagnostic tool, not a normative contract unless it
  contains an explicit fail-closed invariant.

## Reclassification — actual Workflow owners in PR #753

| Workflow / Job | Classification | Action |
| --- | --- | --- |
| Repository CI / `validate` — exact-head, event, dependency, integration authority | STATIC | Keep permanent small kernel |
| Repository CI / legacy namespace census, stage-specific retirement claims | MIXED / NEEDS_SPLIT | Keep genuinely permanent prohibition if adopted; move particular migration receipts to Dynamic |
| Harness Code CI / harness pytest | REGRESSION TEST | Keep while code is maintained |
| Physics Code CI / `physics_code_validate` | REGRESSION TEST + MIXED | Keep general tests and universal invariants; split out Issue/retirement gates below |
| Physics Code / FDEG structural, functional, transition, cache, A–D tests | REGRESSION TEST | Keep reusable analyzer unit tests, not one-time evidence receipts |
| Physics Code / code7 FDEG retirement HEAD snapshot/upload | DYNAMIC — task-scoped | Move to active retirement task; remove on accepted cutover |
| Physics Code / Issue43/45 and Issue89 final guards | DYNAMIC / MIXED | Extract lasting invariants and tests; retire historical acceptance prose and fixed studies |
| Physics Code / Issue17, 26, 176 production ownership/source guards | DYNAMIC / MIXED | After task acceptance preserve lasting physical behavior regressions, retire Issue acceptance gates |
| Physics Code / `issue541_group_a_evidence` | DYNAMIC — acceptance audit | Retire only after each Group A scope has explicit accepted retirement/retention decision |
| Physics Code / `issue541_arch_replay_p0` | DYNAMIC — DD/S6 replay protection | Keep task-specific approval/evidence gate while active; STATIC rule against unauthorized P3 remains |
| Physics Native / `runtime-smoke` | REGRESSION TEST + DYNAMIC pinned release evidence | Separate general runtime smoke from check of a frozen historical OCI image |
| Physics Native / `boltzmann-eepf-controls` | REGRESSION TEST + DYNAMIC development output | Keep useful solver controls; private-input candidate artifact build/upload only for active development |
| Physics Native / `issue402_core_four_native_p2` | DYNAMIC — four-cutover acceptance | Retire specific receipt and special Job after acceptance; preserve needed native behavior tests |
| Physics Native / `plasma_native_regression` | REGRESSION TEST | Keep current-source Native integration tests, not an Issue-defined permanent contract |
| Physics Native / `issue541_arch_dd_native_p2` | DYNAMIC — DD acceptance | Retire once scope accepted; keep relevant native fixture regression |
| Physics Native / `issue541_arch_s6_hybrid_native_p2` | DYNAMIC — S6-417/941 acceptance | Retire once accepted; preserve needed native case regressions |
| Physics Legacy Audit / `issue541_evidence_identity_p0` | HISTORICAL EVIDENCE / retired Dynamic candidate | Preserve historical receipt; manual interim lane, then remove obsolete task contract |
| Physics Legacy Audit / `issue402_s6_reference_receipt` | HISTORICAL EVIDENCE / retired Dynamic candidate | Preserve archive receipt; no always-on verification |
| Physics Legacy Audit / `issue402_legacy_p0_inventory` | AUDIT TOOL | Only run on request; not a pass/fail source-usage contract |
| Physics Legacy Audit / `issue402_json_rate_p0` | DYNAMIC — prior task replacement | Manual reproduction while acceptance history confirmed; maintain reusable regression separately |
| Physics Legacy Audit / `issue402_ideal_gas_p0` | DYNAMIC — prior task replacement | Same: verify acceptance before deleting temporary gate |
| Physics Legacy Audit / `issue402_core_four_p0` | DYNAMIC — prior task replacement | Same: its history/negative controls do not become universal requirements |
| Physics Legacy Audit / `issue402_reaction_material_p0` | DYNAMIC — prior task replacement | Same |
| Repository Diagnostics / `artifact-api-probe` | AUDIT TOOL / DYNAMIC when diagnosing uploads | Manual only; delete temporary probe when diagnostic task closed |
| Issue402 FLOW maintained Native P2 | DYNAMIC + REGRESSION TEST | Reassess accepted cutover separately; retain runtime behavior coverage if still needed |
| Explicit ARCH DD/S6 P3/P4 manual replay routes | DYNAMIC approval/execution routes | Remain authorized manual operations until scope closes; never imply science acceptance |

**No unverified acceptance is inferred from the presence of a successful
historical job.** Rows labeled `DYNAMIC` are candidates for scoped review,
not preauthorized deletion.

## Retire/keep decision procedure

For every legacy contract or guard:

1. **Permanence test:** Is this condition binding even if *all* current Issues
   have closed and no related capability is being developed? If yes, STATIC.
2. **Task test:** Does it reference a specific migration, Issue, exact historic
   run, archive or acceptance target? If yes, DYNAMIC or HISTORICAL EVIDENCE.
3. **Value test:** Would deleting this checker allow a *current* production
   behavior regression to pass? If yes, preserve its relevant regression
   assertion in the maintained test suite or promote a truly general invariant.
4. **Authority test:** Has the task actually been accepted, required evidence
   archived and outstanding consumers resolved? If not, HOLD the retirement.
5. **Cleanup test:** After authorization, remove the temporary registration,
   Job, Guard, manifest entry and fixture-specific owner checks. Document
   retained tests and archived evidence. No orphan hardcoded requirement.
6. **Negative proof:** Inject missing verifier, wrong HEAD, unauthorized event,
   stale proof, false PASS and omitted required regression; ensure rejected.

## Why the existing `repository_ci_scope_v1.json` is transitional

It currently freezes the Job names of the original 17-job Repository CI and
step names from the old `validate`, including task-specific Issue402/541
lanes. These are **migration inventory/evidence**, not STATIC obligations.
Long-term replacement is a small static policy enforcing *permanent
invariants* plus task-scoped Dynamic acceptance records with a verified
retirement gate. Do not create a larger eternal per-Job inventory.

A discoverable verifier registry may help implement either category but is
**not the definition of Dynamic Contract**.

## Relationship to PR #753

PR #753 removes seven historical/duplicate P0 jobs from *automatic* Physics
Code CI and preserves their commands in the interim manual `Physics Legacy
Audit`. That is **run-scope reduction, not final retirement**. Final deletion
of their temporary contracts and legacy audit wiring requires per-scope
evidence/acceptance verification. The production Physics test suite and
Native P1/P2 are not removed by this classification document.

Follow-up authority: #754. Historical CI retention work: #752 / PR #753.
