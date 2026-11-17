# Issue #633 — P21/P22 New-only CI/Workflow handoff

**Observed main:** `8263fbc1801f213b98183ba4876299041cd01dac` (2026-11-17).
**Sources:** ion_1 PR #659 `083a52d96aa2a3e9cef84bcc7426a3bf2a7497cb`; ion_2 `issue-633-p04-json-selection-20261117@3822d68`; ion_3 `issue-633-c2-static-contract-20261117@5d48e78`.
**State:** READ_ONLY_AUDIT_DONE; inactive test/Workflow staging only. P18–P24 NOT_VERIFIED; P3 NOT_RUN; SCIENCE_HOLD.

## CI and legacy Hybrid impact

| Surface | Current constraint / required repair |
|---|---|
| `physics_app/ci/check_electron_molar_representation_contract.py` | Still checks the old `PhysicsFVLogMolarElectronTransport` factories. Rebind to the new unprefixed factories only with the P10–P13 caller migration and retained residual/units contracts. |
| `tests/test_retired_legacy_physics_owners_contract.py` | Still requires old FV file to exist. Update together with the approved old-owner retirement, not before. |
| `tests/test_issue402_hybrid_json_s6_owner_preflight.py` | Requires historical ion Native `ni_time` etc. Preserve as historical Hybrid regression, not New-only pass/fail oracle. |
| `.github/workflows/issue402-flow-native-p2-regression.yml` | Existing `physics_app/**` trigger requires unchanged #541 FLOW P0/P1/P2 evidence; do not bypass or relabel. |
| `.github/workflows/ion-fvm-hybrid-staged-dt.yml` | Existing PR/push path filters launch 150/200-step historical Hybrid runs. #538 only updates FV file paths, not events. Do not add New-only paths or silently disable historical gate. Separate change/approval required for event policy. |
| `ci/workflow_templates/general-ci.yml` and `.github/workflows/ci.yml` | Same Git blob on observed main; when P21 changes general CI, edit template and generated output together, then run harness and surface Guard. |
| `.github/workflows/issue541-arch-dd-p3-replay.yml` and `.github/workflows/issue541-arch-s6-p3-p4-replay.yml` | KEEP UNCHANGED. Manual approval, source and artifact custody are separate #535/#541 contracts. Do not reuse these for New-only. |

## New-only admission contract, per case 417 and 941

1. P18: integrate ion_1–3 at one exact HEAD. Reject both `log_O2p/Om/Op` and historical `log_ni/nm/nop` residual Native FV owners; prove factory and source/consumer readiness. 
2. P19/P20: materialize exactly eleven ordered New-only .i layers plus integrated `unified_s6_<case>.json`. Only *scratch* may retire fourteen in-scope ion Native kernels and twelve FV BCs. Original .i/ZIP/block SHA receipts must remain immutable and independently read back.
3. P0: `ci/guards/issue633_new_only_p0_p2.py` examines *actual* materialized layer and JSON bytes, exact case/source SHA, FEM=e/FVM=O2p Om Op, explicit potential and no selected ion Native kernels/BCs. Requires manifest `issue633.new_only_11layer.v1` with `mode=new_only`, `case`, `source_sha`, `ordered_layers`. **P0 input validation is not proof of 12+12 instantiated FV objects.**
4. P1: build `physics-opt` on the same HEAD in pinned `physics-build-base@sha256:2c3352da4f5c1b2ae98475fc01463ad0cdbc6ce7d221ce55055ddea152182008`; independently retain build-success log, source and binary SHA256.
5. P2: opt-in `--binary <same-job physics-opt> --output <new evidence dir>` invokes `--check-input` only. Require actual syntax success and an independent Runtime Warehouse object census (12 FV kernels, 12 FV BCs, 3 Wall Flux Materials and surviving consumers). P1/P2 admission is **HOLD** until real build/check-input evidence exists.
6. P3: candidate `ci/workflow_templates/issue633-new-only-400w-100us-manual.DRAFT.yml` deliberately remains outside `.github/workflows/`. Promote only after P18–P24 exact-head PASS, dedicated New-only runner and second explicit approval `ISSUE633_NEW_ONLY_400W_100US_BOTH_CASES_APPROVED`. Matrix 417/941, 400 W, 100 μs, maximum 360 min per case with solver timeout 18000 s. This separate approval is **not granted by preparing the template**.

## Current blockers and approval gates

- ion_2/ion_3 sources have no same-HEAD real Native P1/P2 readback; ion_2 source-shape asserts four FV kernel types per selected species but does not certify Runtime Warehouse uniqueness.
- ion_3 Guard currently accepts a **synthetic** rendered `[FVBCs]` and `[FunctorMaterials]` input, not proof that dynamic Physics generation created those objects.
- The current `run_chemistry_s6_p3_once.py --hybrid-json` retains Native ion ownership; it **must not** run as New-only P3.
- New-only 11-layer cutover and dedicated 400 W /100 μs New-only runner are not yet present on verified main. Do not activate the template; no automatic long P3 is authorized.
- #535/#541 original Workflow files, archive retention, SCIENCE_HOLD and independent replay approval remain unchanged.

This bounded staging work does not change live GitHub Actions Workflow YAML, general CI, Physics sources, historic input, secret rates, or a P3 dispatch.