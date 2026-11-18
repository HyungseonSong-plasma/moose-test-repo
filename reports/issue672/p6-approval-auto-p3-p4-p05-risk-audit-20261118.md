# #672 / P6-D2+C trigger guard — #535/#541 approval, costly P3/P4 auto-fire, P05 bypass review

> STATUS: `AUDIT_COMPLETE_SOURCE_ONLY / INTEGRATION_HOLD`. As of 2026-11-18; exact reviewed Draft PR #665 HEAD `74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f`; main `ebcfd9e662bc40f0473d8da05da95d11b61789f8`. Read-only source and issue approval audit. Did **not** dispatch a workflow, run a timestep, change any workflow, modify PR #665/main, or claim P05 Native PASS.

## 1. Authorization boundary — #535 / #541

| Contract | Recorded operator authorization | Does not authorize |
|---|---|---|
| Wave1 original Issue402 workflow cleanup | #535 scoped first six D2/D3/D4/A3/A4/B: external/private/dynamic-caller residual-risk acceptance and existing replacement P0/P1/P2 *within the original six obligations*, operator comment [#6941923213](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/535#issuecomment-6941923213) | arbitrary workflow rewrites, universal caller-zero proof, P3/P4, New-only science |
| ARCH DD and S6 archived executables | #535 separate operator approval [#6943043495](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/535#issuecomment-6943043495): unknown caller risk accepted for **two** archived workflows; mutable, user-managed private Drive accepted instead of WORM | WORM claim, physical model changes, New-only migration or broad API caller-zero |
| ARCH S6 maintained historical Hybrid P3 | Manual `workflow_dispatch`, explicit `source_sha` and `p3_approval=ISSUE541_S6_400W_100US_BOTH_CASES_APPROVED`, both original 400W/100us cases 417+941, target scientific source `8263fbc1801f213b98183ba4876299041cd01dac` | automatically launching a new run on push/PR, repurposing a new HEAD/new-only model, extended science P4 |
| ARCH S6 physical execution and closure | [manual P3 run #44050874900](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44050874900) terminal SUCCESS 417+941, artifacts #14327600496/#14333842379; narrow operator acceptance of 400W/100us Hybrid electron-density PNG comparison; [#535 receipt #6954901258](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/535#issuecomment-6954901258) | full 3D/multi-physics parity or current New-only cutover |
| Wave1 operational retirement | [#541 final receipt #6955180301](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/541#issuecomment-6955180301): original **10/10** workflows `RETIRED_VERIFIED`, old executable copies 0/10 after merged PR #666 | closing remaining #535 Issue #1 work, auto P3 reactivation, full science or #633 acceptance |

**Decision:** Keep archived historical Hybrid as immutable interpretation/reference, with authorized manual replay only. **Public D's historical Hybrid contract is not silently replaced by New-only.** New-only PR #665 must use a separately approved new-only P0/P1/P2 lane, exact producer ownership, and a new explicit decision before costly P3/P4; do not reuse the ARCH historical manual approval token or the old reference science result as scientific equivalence. `SCIENCE_HOLD` remains outside the accepted Hybrid electron-density PNG scope, P4 remains `DIAGNOSTIC_ONLY` for the historical #541 replay.

## 2. Exact current executable trigger surface

| Current path / Git blob | Current event | Actual potentially expensive activity | Risk / disposition |
|---|---|---|---|
| `.github/workflows/issue541-arch-s6-p3-p4-replay.yml` / `6c673628eac4693abe0d74b04fc31578a39b3971` | **Only `workflow_dispatch`** | Two 400W/100us Hybrid S6 P3 jobs with 360-minute timeout, typed approval + exact SHA check **before checkout** | **CONTROL_PRESENT**. Do not append push/PR/schedule, duplicate dispatch, or point to New-only source without new approval. |
| `.github/workflows/issue402-canonical-s6-d-once.yml` / `6d8eb34b45876dcec08714dba7d8cb68cd19862a` | **main `push`**, exact self-path only | Matrix **417+941**, actual `run_canonical_s6_p3_once.py` each 100us and P4 reference diagnostics, timeout-seconds **19800** per case, job timeout 360 minutes | **HIGH: LATENT AUTO-P3** if that YAML is modified on main. No `workflow_dispatch`/typed approval. Not currently triggered by PR665 because the workflow file is not in the PR diff. Never modify/re-enable without explicit fresh owner approval and a manual event/cost guard. |
| `.github/workflows/ion-fvm-hybrid-staged-dt.yml` / `230e4367e7a688f297747b7f03bb0fdfaf4e4d23` | **main push + PR to main + manual dispatch** with path filters | Builds PhysicsApp, preflight `--check-input`, then actually calls PhysicsApp transient for **200-step** and **150-step** staged-dt jobs. Job 45min; inner timeout 35min | **HIGH: PR665 matched auto long-run trigger** because current PR665 changes `physics_app/src/functormaterials/IonWallFluxMaterial.C`, an included filter. If P2 later passes, automatic transient can launch without a science token. Historical `RETIRED_GROUNDED_SHEATH_BCS` may fail before run, but this is not an authorization guard or guaranteed cost stop. |
| `.github/workflows/issue402-flow-native-p2-regression.yml` / `3f2360f7ae71ed9081dfa55aeba5119f5c44a9b0` | PR to main + manual dispatch | FLOW original D-base 417+941 `run_chemistry_s6_p2_only.py` + EI10/EI16 native fixture `--check-input` and P1 build, explicit `P3=NOT_RUN` | **P2_ONLY_SAFE_BY_SOURCE**, no observed direct P3 invocation. Does not establish New-only #633 acceptance; preserves separate Hybrid/legacy D/FLOW contract. |
| `ci/guards/workflow_surface_guard.py` / `744b7a40922be3ea4a945f22bcd5c5c374499f67` | static CI policy | Enforces known manual-only #541 routes; however `one_shot_errors()` explicitly *allows* `push main` + self-path for any `issue*-once.yml` | **COST_GUARD_GAP**: workflow-surface PASS does not prove that an approved costly 100us P3 cannot fire on a main YAML edit. |
| `.github/workflows/ci.yml` (main) | main push + PR | standard validate/static and bounded smoke; Issue402 S6 P3/P4 receipt job is a manifest check, not physical full P3 | No direct ARCH full-100us dispatch observed in CI source. Do not substitute P4 reference receipt job for actual science execution. |

**Direct trigger links:** [canonical D one-shot](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f/.github/workflows/issue402-canonical-s6-d-once.yml); [Ion-FVM staged dt](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f/.github/workflows/ion-fvm-hybrid-staged-dt.yml); [ARCH manual route](https://github.com/HyungseonSong-plasma/moose-test-repo/blob/74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f/.github/workflows/issue541-arch-s6-p3-p4-replay.yml).

## 3. P05 bypass surface and failure mode — do not confuse scoped checker with always-on certification

| Source / exact Git blob | Observed implementation | Risk |
|---|---|---|
| `DDContinuityEq.C` / `13b25226d463b8fd1e4acaee16358f8f17d710a0` lines 252–369 | `checkIntegrity()` returns immediately for `dont_create_kernels=true` (line 258) and before FV Warehouse checks if `_fvm_species.empty()` (line 268); otherwise queries FVElementalKernel + FVFluxKernel and FVFluxBC + FVDirichletBC in `TheWarehouse` and rejects unexpected, duplicate, or missing names/types on each selected FVM `log_<species>` | **CONDITIONAL COVERAGE**. With generation disabled or no selected FVM species, this code cannot certify 12 FV Kernels + 12 FVBC. P05 success/absence by itself does not certify the intended selected chemistry. This is not evidence that production New-only actually bypassed P05. |
| `ci/p1_ion_new_only_preflight.py` / `c913bfbced72a9c37d0ed2214a44e5dd31657b35` lines 56–81 | For `new-only`, any explicit `dont_create_kernels` is rejected via `P1_BINDING_ONLY_BYPASS_FORBIDDEN`; empty *combined* FEM+FVM selection rejected; duplicate selected species rejected. | **VALID CONTROL for `dont_create_kernels`**, not a blanket P05 bypass. But examined New-only branch has **no `set(fvm)=={'O2p','Om','Op'}` acceptance assertion**; equality to those three is explicitly present only in the **legacy-hybrid** branch (line 418). A modified e-only/partial FVM input could skip the intended FV P05 scope unless another gate stops it. Full P0 acceptance of such a mutant was NOT executed/proven. |
| Same P0 lines 140–154, 405–442 | Native FV-owner scanning tracks only state variable names from `fvm_species` (`log_<selected species>` plus legacy names), and the output says `runtime_generated_kernel_bc_count=NOT_VERIFIED_P0_ONLY`. | **SCOPE-DEPENDENT OBSERVATION**: shrinking FVM selection also shrinks what native owners P0 checks. A P0 static PASS is not a TheWarehouse PASS. |
| Actual #671 independent D8 diagnostic | Both S6 cases actual `--check-input` and 12+12 inventory from isolated instrumentation branch, with true wall/residual sample. | **VALID PROBE ONLY**; not exact latest PR665 source/binary and not full P5-X release acceptance. [#671 numeric receipt](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/671#issuecomment-6978801446). |

**Required fail-closed acceptance:** before any Native P3/P4 or long-run dispatch, (a) exact current/approved SHA+tree and actual OCI+binary SHA; (b) `P0 new-only`, case-specific 11-layer and JSON exact original/hash; (c) `fem_species=['e']`, `fvm_species=['O2p','Om','Op']` **exactly**, `dont_create_kernels` absent, `fvm_kernel_ownership` absent, `[Physics]/[Plasmas]/[Transport]/[Chemistry]` active; (d) Native P05 actual TheWarehouse 12 ion FV Kernels+12 ion FVBC with exact name/type/variable and no legacy FV owner; (e) electron 8 FEM BC and unique wall/current Functor owners; (f) protected EI rate stages inside same job and all original SHA restoration/cleanup. Any missing evidence means HOLD, not empty-subset PASS.

**Required P05 negative controls:** reject empty FVM selection (while FEM e exists), partial FVM missing O2p/Om/Op, `dont_create_kernels=true` or even explicit false in New-only input, extra Native FV Kernel/BC for selected species, missing/generated BC, missing C2 owner, changed JSON input case, wrong `source_sha`/binary, and P05 not actually invoked. Run with distinct Scratch and source-retained SHA; assert specific error and nonzero Native exit, never `CI SUCCESS` alone.

## 4. Disposition / required changes (NO production mutation in this audit)

1. **Public D** — `KEEP_HISTORICAL_HYBRID_REFERENCE`, `NEW_ONLY_CUTOVER=HOLD_NEEDS_SEPARATE_CONTRACT_AND_NATIVE_P05`. #535/#541 operational retirement approvals do not select public D New-only over Hybrid or prove physical wall/sheath equivalence. P6-D2 decision table is ready; P6-D4/D5 require explicit authority, source and runtime proof.
2. **ARCH** — protect `.github/workflows/issue541-arch-s6-p3-p4-replay.yml` `workflow_dispatch`-only + typed approval + exact source; no retrospective rerun. Old 10 original Workflow retirements remain accepted; no auto reactivation.
3. **Canonical D old one-shot** — before modifying `issue402-canonical-s6-d-once.yml` on main, **review/approve a manual-only replacement or inert retirement** with source/evidence preservation. A direct edit itself launches 2×100us on main, so a safe trigger migration must account for the transition event (e.g. PR-only review and explicit controlled rollout); do not blindly retarget to main or remove without audited consumer proof.
4. **Ion-FVM 150/200** — urgently separate PR/main P0/P2 fast path from long solver job; long-run should require explicit manual typed approval + source SHA + resource/time budget. Path `IonWallFluxMaterial.C` in PR #665 matches current PR filter, so avoid accidental merge/run acceptance. Existing two jobs' `RETIRED_GROUNDED_SHEATH_BCS` failures are a physics-compatibility HOLD, not a substitute cost/approval gate.
5. **P05** — add explicit S6 exact FVM selected-species invariant on New-only P0 plus native guard/inventory assertions. Retain `dont_create_kernels` as valid for narrow historical binding-only tests, but prevent it from satisfying P05 acceptance. Reject `P05=PASS` when no Warehouse object census, mismatch or wrong execution HEAD.
6. **Integration ownership** — P6-X/C3 alone changes `.github/workflows/ci.yml`/generated workflow templates and shared CI triggers after a reviewed decision. Any workflow path edits, auto-run suppression, or New-only science dispatch require a separate approved mutation plan. P5-X alone promotes final Native P2; historical SCIENCE_HOLD remains for New-only P3/P4.

## 5. Independent read-only checks and matrix

On PR #665 exact reviewed source `74a2b0f…`, **17/17 static source predicates PASS**, covering manual event/approval/exact SHA/two-case ARCH route, canonical D `push-main` self-path 100us without token, Ion-FVM push+PR 150/200, P05 early returns and strict selected `TheWarehouse` queries, New-only P0 explicit binding-only rejection, missing strict selected-three FVM check in examined branch, FLOW P2 only, and P0 `NOT_VERIFIED_P0_ONLY` disclaimer. Confirmed via exact repository blobs:

- ARCH manual route `6c673628eac4693abe0d74b04fc31578a39b3971`.
- canonical D auto-P3 route `6d8eb34b45876dcec08714dba7d8cb68cd19862a`.
- Ion-FVM long-run route `230e4367e7a688f297747b7f03bb0fdfaf4e4d23`.
- FLOW P2 route `3f2360f7ae71ed9081dfa55aeba5119f5c44a9b0`.
- workflow guard `744b7a40922be3ea4a945f22bcd5c5c374499f67`.
- DDContinuity P05 `13b25226d463b8fd1e4acaee16358f8f17d710a0`.
- P0 selected ion audit `c913bfbced72a9c37d0ed2214a44e5dd31657b35`.
- FLOW CLI `96c8ca548392a1ad08334b87b082dd1595893070`.

17/17 source predicates are **not** a real mutated Native failure matrix or a dynamic workflow dispatch test. No expensive solver, manual dispatch, change to a production workflow or protected/private EI rate access was made. High-risk routes are classified by literal file code/events; dynamically invoked private callers cannot be globally ruled out.

### Final gates

| Gate | Decision |
|---|---|
| #535/#541 original 10 retirement within signed scope | `PASS_SCOPED_OPERATIONAL` |
| Approved historical ARCH full two-case P3 source-bound run | `PASS_HISTORICAL_HYBRID_ONLY` |
| P3/P4 auto-trigger safety of **all** relevant active lanes | `HOLD_HIGH_RISK_TWO_AUTOMATIC_ROUTES` |
| Public D Hybrid-to-New-only authority | `HOLD_SEPARATE_APPROVAL` |
| P05 Warehouse coverage when selected species and generation active | `PASS_STATIC_GUARD_EXISTS` |
| P05 zero/partial-selection bypass resistance on New-only P0 | `HOLD_STATIC_CONTRACT_GAP` |
| PR #665 exact latest Native P05 and all N1–N8 | `HOLD_P5_X` |
| New-only scientific P3/P4 and long-run parity | `SCIENCE_HOLD` |
