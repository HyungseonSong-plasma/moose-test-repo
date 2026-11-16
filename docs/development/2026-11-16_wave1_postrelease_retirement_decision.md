# Wave1 post-release retirement and residual legacy audit

**Authority:** [Issue #535](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/535) (retirement policy), [Issue #541](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/541) (Wave1 ten original workflows). **Main pinned source:** `4738c56b79c7f9e08340d705339ec2a4a19ad456`, 2026-11-16 UTC. This is a **new current-state supplement**, not a rewrite of the historically valid draft/KEEP_HOLD baseline snapshots.

**Exact source IDs and 26+14 enumerations:** [machine-readable inventory](2026-11-16_issue535_postrelease_inventory.json). This PR changes only two new documentation files; no executable workflow, Physics source, CI Guard, artifact, archived source or historical branch was modified.

## Verified Release and Workflow Surface result

- [Wave1 #578](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/578) merged into main at `02910c0ea7c91fd34f86f117b2d68c3e67890f2a`. [Postmerge CI fix #655](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/655) merged at `4738c56b79c7f9e08340d705339ec2a4a19ad456`.
- [Latest main Repository CI #43976673554](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43976673554) **COMPLETED SUCCESS**, including `workflow_surface_guard.py --self-test/--check`, Workflow Harness, the zero-legacy architecture census and active-CI surface check. Its main push policy **skips** the Native P1/P2 jobs; do not mislabel them as postmerge Native runs.
- [Exact premerge source CI #43972605776](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43972605776) **17/17 SUCCESS** at `1efdd922096df10239cff8adc132e8f3811c1a63` including real pinned-OCI CORE/ARCH DD/S6 P1/P2 and generic Native regression. Independent [FLOW Native #43972605750](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43972605750) and [SOL #43972605779](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43972605779) both SUCCESS at the same SHA. No P3 was dispatched for this release assessment.
- All **ten** Wave1 Issue #541 originals are **absent** from current main's executable `.github/workflows/`. Eight original Git blobs were directly retrievable by pinned SHA at this audit. Two ARCH original sources are additionally preserved as byte-identical non-executable files in `docs/development/archive/`: DD `068ef7f78b84b45dbf8c678522ada049d4a42b7a`, S6 `485439a723584ca5bbc8632a86c53574b0b1eb9a`. Default-branch manual-only DD/S6 replacements are REQUIRED by current Guard.

**Verdict:** `WORKFLOW_SURFACE_POLICY=PASS`; `WAVE1_ORIGINAL_EXECUTABLES=0/10`; `FORMAL_RETIREMENT=2/10`; `FORMAL_HOLD=8/10`. An absent executable YAML and a green Guard are **not** conclusive evidence of original contract retirement, caller-zero, or scientific parity.

## Wave1 ten original Workflows — one disposition per file

| Package | Removed original | Original Git blob | New formal disposition | Acceptance or remaining blocker |
| --- | --- | --- | --- | --- |
| D1/A1 (CORE) | `issue402-dd-json-boundary-p0-p2-once.yml` | `bbebff910db3` | **RETIRED_VERIFIED** | P0-P2 ONLY: operator attested no external callers; 19 owner push runs; historical #606 cutover; source ZIP hash backup; final exact PR-head CORE Native P1/P2 pass |
| D2 (CORE) | `issue402-sccm-fixed-gas-p0-p2-once.yml` | `9cfa70c6843f` | **KEEP_HOLD** | External and dynamic caller-zero not independently established |
| D3 (CORE) | `issue402-species-initial-composition-native-once.yml` | `f11aa0de000f` | **KEEP_HOLD** | External and dynamic caller-zero not independently established |
| D4 (CORE) | `issue402-species-live-ic-inlet-native-once.yml` | `c6068680c0c7` | **KEEP_HOLD** | External and dynamic caller-zero not independently established |
| A2 (FLOW) | `issue402-legacy-symbol-audit-once.yml` | `1931f0b99095` | **RETIRED_VERIFIED** | Previously accepted #535; #602 historical cutover; owner attested no external PAT/private controller; maintained P0 inventory tests |
| A3 (FLOW) | `issue402-rate-coef-ideal-gas-native-once.yml` | `64164c097ec8` | **KEEP_HOLD** | External and dynamic caller-zero not independently established |
| A4 (FLOW) | `issue402-reaction-material-reduction-p0-once.yml` | `5e433b5c56f3` | **KEEP_HOLD** | External and dynamic caller-zero not independently established |
| B (FLOW) | `issue402-reaction-reduction-native-once.yml` | `91313152e7e7` | **KEEP_HOLD** | Old multi-path self-trigger retired from main; external and dynamic callers not independently established |
| DD (ARCH) | `issue402-dd-json-p3-smoke-once.yml` | `068ef7f78b84` | **KEEP_HOLD** | Original archived exact byte; DD two-step live run source-bound only; WORM and external caller exhaustiveness not proven |
| S6 (ARCH) | `issue402-hybrid-json-s6-p3-p4-once.yml` | `485439a72358` | **KEEP_HOLD** | Original archived exact byte; 417 941 three-step P3 source-bound only; full maintained 100us replay and WORM unproven |

**A1 scope qualification:** New `RETIRED_VERIFIED` recognizes the *P0/P1/P2 DD boundary original* only: accepted previous operator declaration of no external callers, documented 19 historic owner `push` executions and default-branch caller scans, [historical original cutover #606](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/606), source/ZIP hash-preserving backup, and full source-bound CORE P0/P1/P2 CI now merged and verified. It **accepts explicitly attested operator risk**, not an exhaustive proof against every off-platform actor. The separate ARCH DD P3 old original remains a **different** workflow and formal HOLD. A1's earlier `STAGED_DELETE_KEEP_HOLD_INTEGRATION` baseline truthfully describes its **earlier snapshot**; do not edit that historical record retroactively.

**A2 qualification:** Retains the already accepted `RETIRED_VERIFIED` P0-only decision and previous operator-attested absence of external PAT/private controller. For the eight HOLD entries, replacement functionality may be passing while full dynamic/external caller, unique replay or archival retention gates remain unresolved. **None** of those eight may be promoted automatically by this green release CI.

## Residual 26 other main one-shots — no delete authorization

All 26 were read by exact current Git blob. Their **declared** events are `push` only, `branches: [main]`, `paths: [.github/workflows/<same file>]`; they currently satisfy Surface Guard. Editing such a YAML may still trigger its job. This is **trigger inventory**, not a full invocation graph, consumer-zero proof, science-run replay or cost approval. Every entry remains `KEEP_PENDING_OWNER_CALLER_AND_EVIDENCE_AUDIT`.

| Current workflow | Exact Git blob | Disposition |
| --- | --- | --- |
| `issue202-maxwell-once.yml` | `c46bcc78659d8f179b1a518fcbcbf25476150ad1` | KEEP / audit pending |
| `issue282-historical-rz-e2a-once.yml` | `7e04362a03248f778a6ebf300a39f8541bd8a16e` | KEEP / audit pending |
| `issue282-rz-jitoff-once.yml` | `3fd69c82bf962692fb43cfe3d1af5c11414561ab` | KEEP / audit pending |
| `issue310-relaxation-once.yml` | `6001ef71540d47ec59d3b013c1f93728da1fe616` | KEEP / audit pending |
| `issue395-ground-state-three-power-once.yml` | `4bcea0ba352319c1b513ec96ca06426584712ee5` | KEEP / audit pending |
| `issue395-mixed-o3p-o1d-400-1000-once.yml` | `57e29713060a7cc26254633bf3afd04c5d5678c2` | KEEP / audit pending |
| `issue395-mixed-o3p-o1d-initial1e15-once.yml` | `8abdd8f46896448611f41292511a9510c5d37c15` | KEEP / audit pending |
| `issue395-mixed-o3p-o1d-zero-initial-once.yml` | `87c48bb222e776468070f92feee75cd7cfdbc022` | KEEP / audit pending |
| `issue395-o2p-dr-ab-once.yml` | `9c42e5738f7354b03898cdb78307f9441ac34e9f` | KEEP / audit pending |
| `issue395-o2p-dr-zero-o-once.yml` | `7f85af30bb79670af04bd43fdd4132e60d5e684b` | KEEP / audit pending |
| `issue395-oxygen24-400-1000-once.yml` | `7b71b4259bd5a59382094458bb67b2c61ef65b4f` | KEEP / audit pending |
| `issue395-pure-o2-inlet-mixed-400-1000-once.yml` | `96e84a4ef9a7fd6150016fddc7ad34ea64b56bbd` | KEEP / audit pending |
| `issue395-step0-no-diss-control-400-1000-once.yml` | `1d4b6cd1c266d426887d9aca3e950a996e5d5104` | KEEP / audit pending |
| `issue395-step1-diss-off-pure-o2-400-1000-once.yml` | `a1d4143ef65b663625f26173041a0f7b4ceb512f` | KEEP / audit pending |
| `issue402-canonical-s6-d-once.yml` | `6d8eb34b45876dcec08714dba7d8cb68cd19862a` | KEEP / audit pending |
| `issue402-chemistry-p3-once.yml` | `ff5433fa9dd92fc2bca66833ed3860d81406aa74` | KEEP / audit pending |
| `issue402-electron-fem-hybrid-p3-once.yml` | `8f3658a26ee3de6c81c9157aad5b6dee075ce338` | KEEP / audit pending |
| `issue457-c0-400-100us-once.yml` | `2947edc63ffeb0cf6e9d9bef3d074f554be852b9` | KEEP / audit pending |
| `issue457-oxygen-c0-preflight-once.yml` | `50fcfeab30299abe77d1409804798623d5eedb1b` | KEEP / audit pending |
| `issue471-ad-parser-closure-once.yml` | `b99d47dfeb373636b6251458a86330b5a4576418` | KEEP / audit pending |
| `issue477-first-three-400w-native-maps-once.yml` | `39b8cf6f7c9dffc0df068106269e3d6b6576d3af` | KEEP / audit pending |
| `issue477-s3-401-op-generation-native-maps-once.yml` | `d20f7b12866b877f501d7fcfcd110307b388db14` | KEEP / audit pending |
| `issue477-s5-o2-consumers-4plus4-delay-once.yml` | `97688e103511f844ae6d181a64fa876e26a67d58` | KEEP / audit pending |
| `issue477-s6-combined-407-2069-h25-once.yml` | `111b8be4121e427ff383bf742a15f260f84e5da5` | KEEP / audit pending |
| `issue477-second-base-3lookup-native-maps-once.yml` | `c9cb9a1165323240b86d494b0a5760638a28ba3b` | KEEP / audit pending |
| `issue493-public-bc-results-p4-once.yml` | `729d5cc9a8530d7dffadaabd3440c58aaaa5b6ca` | KEEP / audit pending |

These break down by original issue: #202 (1), #282 (2), #310 (1), #395 (10), #402 (3), #457 (2), #471 (1), #477 (5), #493 (1) = 26. Do **not** treat them as 26 Wave1 policy violations, nor delete them just because they are named `once`.

## Distinct Issue #1 original retention — 14 of 14 KEEP

The checked original path is `experiments/Issue1_reactor_o2plus_integration/`: **6 canonical `test.json`**, **6 `.i` inputs**, **2 shared checker Python scripts**. For each manifest, `input`, `checker`, `checker_args` link to the original file/checker. Git source identities are in the JSON ledger; summary below.

| Canonical test directory | Original .i SHA prefix | Manifest SHA prefix | Checker/mode | Decision |
| --- | --- | --- | --- | --- |
| `correction_on` | `5c20f5036f03` | `16886ceca94b` | `check_reactor_o2plus.py` (`correction_on`) | KEEP |
| `full_exact_phi_ic` | `a9d7354f8763` | `4e494d56e1c5` | `check_migration_state.py` (`full`) | KEEP |
| `full_zero_phi_ic` | `d883a9bf8f11` | `a662bd12355c` | `check_migration_state.py` (`full`) | KEEP |
| `migration_only_exact_phi_ic` | `9906040c450e` | `7b553ef668d3` | `check_migration_state.py` (`migration_only`) | KEEP |
| `poisson_analytic` | `5b20df833782` | `df860e45ed58` | `check_reactor_o2plus.py` (`poisson_analytic`) | KEEP |
| `self_consistent_2d` | `d2986a9f06b5` | `0a2e86402281` | `check_reactor_o2plus.py` (`self_consistent`) | KEEP |

Checker identities: `check_migration_state.py@359ddccbc6b1cdb9cc1bb2016fe78d5d45fb3fc1` and `check_reactor_o2plus.py@dd24ab29dd0de8015e42280f7584a51e2bdc1dc6`. **Three known direct consumers are still present on main**: `.github/scripts/issue197_h3_migration_audit.py` references the migration-only case; `.github/scripts/issue199_h5_known_charge.py` references Poisson analytic; `tests/test_issue402_retired_charge_poisson_ownership.py` reads self-consistent charge/Poisson input. Beyond literal code search, `physics_harness/execution/workspace.py::discover_manifests` recursively scans `test.json` files under a caller-specified root (CLI `--tests-root`). The default harness root is `tests/`, which is not proof that deleting Issue #1 would preserve explicitly invoked historical suites.

[Draft PR #534](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/534) proposes a separate source-level fixture rewire, but is **OPEN/UNMERGED** and its H3/H5 input-only snapshots do **not** replace the full six canonical cases. No files were deleted or redirected in this audit; Issue #1 stays `KEEP_ALL_14_DELETE_HOLD`.

## Independent HOLD register (not normalized by Release CI)

- `WORM/OBJECT_LOCK=NOT_PROVEN`: previous GitHub/Drive ZIP byte/SHA256/CRC readbacks and history blobs exist, but the **private Drive copies are owner-mutable**. GitHub Actions artifacts may expire. No immutable retention guarantee was established or claimed here; no new Drive object-readback was performed in this audit.
- `SCIENCE_HOLD=ACTIVE`, `P4=NOT_ACCEPTED`: static or `--check-input` P2 is not physical parity. Previous source-bound real [DD two-step P3 #43911477519](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43911477519) and [S6-417/941 three-step P3 #43902067509](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43902067509) are bounded evidence, not a valid new full 400W/100us two-case replay/physics acceptance.
- `EXTERNAL_DYNAMIC_CALLER_ZERO=UNVERIFIED` for each unresolved original. A2 and scoped A1 rely on **documented owner-attested acceptance**, not a claim that code search enumerates private/off-platform systems.

## Next bounded actions, in the approved order

1. For the eight formal HOLD originals: refresh main/source refs, test dynamic/external callers and corroborate unique historical artifact or replay obligations **one file or caller pair at a time** under #535. Record individual KEEP/REWIRE/DELETE/RETIRE decision and exact-head checks; do not retroactively overwrite older snapshots.
2. For remaining 26: run future **per-file** owner/caller/job/cost inventory before proposing removals. The shared `main` self-path trigger means even a YAML edit can invoke expensive jobs; treat production P3 as explicitly cost-gated.
3. For Issue #1: keep all 14. Distinguish the 6 canonical discovery entries from #197/#199 diagnostic snapshots; obtain proof of any future redirected dynamic tests and actual science evidence before considering deletion.
4. For WORM and science: use separate acceptance gates/evidence repositories. Do not conflate A1/A2 operational retirement with regulatory immutable retention or source-to-physics equivalence.
