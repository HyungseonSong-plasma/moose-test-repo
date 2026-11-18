# P6-0 — Parallel receipt integration / common source barrier

**Decision:** `P6_0=PASS_BOUNDED_RECEIPT_INDEX`; `P6_X=HOLD`; `SCIENCE_HOLD`. This is a source/evidence consolidation, not a new Native result, workflow integration, or science acceptance.

## Frozen identity (2026-11-18)

- Draft PR #665 exact HEAD: `74a2b0fbeaf411d9c76cb82a69de1629fa55fa7f`; source tree: `10ab018235f047bf1abc250d3b18005b9156752a`; separate `main=ebcfd9e662bc40f0473d8da05da95d11b61789f8`.
- Historical source: `29d1acc6ef7969908b86719e4b95c73a1565136d`. Historical 417/941 ZIP SHA256: `441eb637c0eefa947ecbc4e14853ab435e553616b8b6a1e1d11928309409bdcb` / `d8643bf2d029a3236876b8912209be61fb85cecadc3125519897e441835d0177`.
- P1-0 actual Hybrid 417/941 final 11-layer: Actions #44182628032 artifact #14372278070 ZIP SHA256 `97333b09ca3017edb04a35b2ceb82398894ddb61f256fee10e4e8cb7ede623db`. P3-X staged 11-layer: #44257739203 / artifact #14406746397 SHA256 `592a7c82834bab841f6a2e1807db305d0eff1e953f50a0dcc6d7e21ff8820111`.
- P4-X 7-provider cutover has been integrated into #665 (source-only). Final reconstructed C0 file SHA256 both cases `2c3bab8a8e28b360dcd54775d91ba13c97401364c709944bc21d6bf0b6d79490`; **full 35-slot P4-X and P5-X final acceptance remain HOLD**.
- New-only JSON Git blobs: 417 `4a05649b42b798f566d5e455ef46be347ea2a461`; 941 `9568e2cae6640a755f9403c4f58e077c801b998c`. Raw JSON SHA256: 417 `ed99493d992c71b30e7a4120646af388894032d262b9af5bf299522629fe24ef`; 941 `2a7d6b191eddf6a92a6bcf74fc818ade8f30836fdd857dc70516f3aa57fa5dde`.
- Public D historical electron lookup is **100-row** SHA256 `994f6b1deece3c53be7fb3e7f9526555d0f9314fd58749bea6346639f08aa387`; New-only S6 electron lookup is distinct **42-row** SHA256 `35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b`. Do NOT transplant one into the other.
- Build OCI digest: `sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008`. W1 actual ELF SHA256 `cab62a4a9caa4d99a82564f31f915f1a7dc14565607712841123a30276d329bc` built at **older HEAD** `05d7ce4...`; no exact-current-HEAD P5-X promotion.

## 24 parallel slots — evidence coverage

**12 independent receipts / 3 indirect coverage / 9 no independently closed slot.** `PASS` in this table never means full New-only Native or science acceptance.

| Slot | Classification | Evidence / limitation |
|---|---|---|
| B1 | Indirect | E1 ledger covers historical Public B 417/941 10-layer P2; separate B1 sign-off absent |
| D1 | Independent / candidate | PR #684 Public D/FLOW transport cutover code + 18-case CI; **not merged** into #665, Native P2 pending |
| D2 | Independent / audit | #535/#541 approval and auto-P3/P4/P05 risk audit; separate cutover authority unresolved |
| D3 | Independent / SHA | Public D original 100-row table, three ion coefficients, 8/8 negatives; Native D still fails |
| D4 | HOLD | No independent dual-case 4-transport-owner cutover acceptance |
| D5 | HOLD | Public D 417/941 actual Native fails missing e transport JSON |
| F1 | Independent / audit | FLOW 417 missing transport JSON; 941 **NOT_RUN** after early abort |
| F2 | Independent / graph | e 5/3 Energy and ion transport Owner graph static PASS; P05/Native after fix not run |
| F3 | HOLD | Native 26 vs Physics 24 FLOW cutover / authority not resolved |
| F4 | HOLD | New FLOW dual-case Native P2 not executed |
| H1 | Independent / proposal | Historical ARCH retain, modern Hybrid KEEP_HOLD; historical compatible P2 scope separate |
| H2 | Independent / negative | Actual latest-head ARCH 417/941 fail closed at Native ni_time P05; 36/36 static controls |
| H3 | Independent / historical Native | Pinned historical #43883076025 attempt 2 target job succeeds, 417/941 exit 0; workflow overall remains failure; **not current-head ARCH PASS** |
| I1 | Indirect | Current-head Ion-FVM two matrix failures at Python RETIRED_GROUNDED_SHEATH_BCS, before Native; no standalone I1 receipt |
| I2 | Independent / physics | C2 adjacent-field wall and old Grounded Sheath are not physically equivalent; separate approval needed |
| I3 | HOLD | Explicit P0/P2-only scope approval missing; do not auto-trigger 1ns/5ns/10ns |
| N1 | Independent / design | Exact new-only P2 CI acceptance schema G0-G6; N2/N3 not implemented/executed |
| N2 | HOLD | Wait P5-X formal source/ELF/libs/OCI identity and C3 single writer |
| N3 | HOLD | No exact-current-head CI replay with one shared binary and both case Native evidence |
| C1 | Independent / audit | ci.yml/template exact byte parity PASS; costly metadata edited PR trigger and fail-closed artifact policy gap |
| C2 | Indirect | D2 audit covers approval/auto-run/P05 risks; standalone C2 final sign-off missing |
| C3 | HOLD | Only central C3/P6-X may change CI/template; not executed |
| E1 | Independent / custody | 11/11 historical/latest ZIP SHA+CRC independently attested, ELF + two libs checked; E1 **branch diverged from source HEAD** and must not be wholesale merged |
| E2 | HOLD | Rolling PASS/KEEP_HOLD and P7 handoff not yet fully accepted |

## Lane and CI evidence

- [Exact HEAD Repository CI #44297212655](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44297212655): **validate job PASS** (1566 passed / 13 skipped), **overall workflow FAIL**. Historical Public B 417/941 P2 passes; current Public D 417/941 fails missing FEM e transport JSON. ARCH Hybrid 417/941 fails on P05 duplicate `ni_time`.
- [FLOW #44297212567](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44297212567): 417 fails for missing e transport JSON, 941 not attempted. [Ion-FVM #44297212333](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44297212333): both matrix jobs fail during input generation with `RETIRED_GROUNDED_SHEATH_BCS`.
- [W2/W3 Native #44300489811](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44300489811): 417 artifact #14425706979 `668815e6...`, 941 #14425516960 `19180959...`, both exit 0. [N1-N8 negatives #44300759948](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44300759948) 16/16 expected rejection; [Warehouse #44297119716](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44297119716) 12+12 each. These use different binary/diagnostic source epochs: **P5-X current HEAD/same-binary remains HOLD**.
- [H3 historical compatible P2](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/43883076025): old source `5d15c405...`, attempt 2 job #134820962860 SUCCESS and two case `--check-input` PASS; whole workflow remains FAILURE from another attempt. H1 had required explicit run authority: confirm that approval separately; never call this modern ARCH PASS.
- P6-D1 candidate [Draft PR #684](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/684) at `3e48a065...` is NOT merged; [independent PR CI #44308677460](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44308677460) SUCCESS at descendant `eb794429...` with only extra one-shot workflow and verification script.

## Current same-head workflow/source pin

| Path | Verified Git blob SHA1 |
|---|---|
| `.github/workflows/ci.yml` | `c8cbd38369108229af7cf2395893a4539f05e024` |
| `ci/workflow_templates/general-ci.yml` | `c8cbd38369108229af7cf2395893a4539f05e024` |
| `ci/workflow_profiles.json` | `6696b4a3ed4e4bc0e7e80e862e64f9c801b0803c` |
| `.github/workflows/issue402-flow-native-p2-regression.yml` | `3f2360f7ae71ed9081dfa55aeba5119f5c44a9b0` |
| `.github/workflows/ion-fvm-hybrid-staged-dt.yml` | `230e4367e7a688f297747b7f03bb0fdfaf4e4d23` |
| `experiments/Issue402_plasma_dsl_g1/public_option_s6_p2.py` | `a6414baf70590b79f4b4ee4cb16c4b9039355f40` |
| `experiments/Issue402_plasma_dsl_g1/run_chemistry_s6_p2_only.py` | `96c8ca548392a1ad08334b87b082dd1595893070` |
| `ci/guards/issue541_arch_s6_native_p2_only.py` | `533dfa16395c041c610130f90d0489300fdd548f` |
| `experiments/Issue402_plasma_dsl_g1/chemistry/prepare_s6_newonly.py` | `d2091291161033a9662b0d583567f9c35d26c006` |

## Approval / P6-X handoff

1. **Immediate read-only:** close B1, I1 and C2 with standalone exact-head receipts; begin E2 P7 provisional decision index. D2+D3 give D4 permission to design the migration, not automatic Native execution.
2. **Lane-specific:** D4 (Public D 4 transport owners), F3 (FLOW 26 Native owners and 5/3 consumers) require contract-preserving disposable cutovers. D5/F4 require separate real Native approval/execution. H3 old P2 PASS is not a waiver for H2 modern fail; I3 requires a new approved non-time-stepping model-specific fixture or KEEP_HOLD.
3. **New-only:** P5-X must accept final exact-head source, one actual ELF + two app libs + OCI and 417/941 full native P2, Warehouse/P05, protected EI, D8 and correct negative tests. Then N2 runner, N3 exact-head CI.
4. **Shared workflow:** only C3/P6-X writes `.github/workflows/ci.yml` and generated template; preserve equality, add edited-only native cost controls and negative guards, avoid public 100us P3 or Ion-FVM 150/200 timestep auto-run, never use job skip or P05 bypass as false PASS.
5. **Close:** rerun current exact-head CI, independently hash all relevant artifacts, issue P6-X PASS/KEEP_HOLD per lane and P7 handoff. `SCIENCE_HOLD`, main merge, Native P3/P4 and historical deletion remain separate approvals.

**Provenance caveat:** P6-0 directly re-read source HEAD/tree, main, CI/template/runner/JSON blobs, referenced receipts and GitHub run/artifact metadata. The E1 11-ZIP byte/CRC and several Native log validations are separately committed worker attestations; P6-0 did not re-download all ZIPs or re-run physics-opt. Evidence-only isolated branch, no workflow/source/input/issue-body mutation.
