# #774 D12 — Actual Public D 100-row Native P2: controlled HOLD, consumer support boundary

> **Do not mark D12 PASS.** D12 physically executed `physics-opt --check-input` for both Public D 100-row S6 cases using the original exact D10 ELF and protected rates. A matching 42-row control passed on both, but each 100-row case failed. Neither failure was classified as an unregistered `PhysicsFVThermalDiffusion`.

## Immutable execution and safety

- Source: [Draft #800](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/800), tested exact HEAD `945679c1470695a19c10feae0f336e8606bcbbe4`, tree `1eee449472c77068531a65caad4774a46357bfb7`.
- [Actions run #45211070728](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45211070728): **job concluded FAILURE** because required 100-row Native P2 success was not achieved, not because the W1 SHA or protected-rate custody failed. Artifact #14834949203; ZIP SHA-256 `e8985757a76fb5c47693a7ec56eaa443f4047156316d530fc1f8563dc4e4f5d1`.
- Original D10 W1 source `05a3cf85...`, run #45199787795, ELF SHA-256 `6afd05d4a4d356fe5132ca28076ba27e06bea93d485ac8a6b39d334bb9a9465b`. All three app ELF/SO member digests validated; **no rebuild**.
- D11 public 100-row generator actually rendered 11 input layers and a distinct JSON per 417/941; 100-row source table and layer hashes verified. Each Native run used the same pinned OCI and five original protected rate files, restricted to `/dev/shm`.
- **Safety:** `protected_rate_cleanup_verified=true`, `protected_data_in_artifacts=false`. No raw Native log or protected values uploaded.

## Matched positive-control matrix

| Case | Current supported 42-row, same W1/OCI/rates | New Public D 100-row | Retired Thermal source detected? |
|---|---|---|---|
| S6-417 | **rc=0, Syntax OK** | **rc=1, FAIL** | No |
| S6-941 | **rc=0, Syntax OK** | **rc=1, FAIL** | No |

Both Public D failures record `native_error=true`, `unregistered_factory=false`, `missing_file=false`, `transport_lookup=false`, `unknown_parameter=false`. Fixed public diagnostic terms are sparse and do **not** establish a root cause. In particular, **the old ThermalDiffusion Factory is not implicated** by current evidence. The correct next task is to derive a safely sanitized first MOOSE error category and repair only the confirmed Public D *input generation/adapter* contract, then rerun 417/941 Native P2 with the same 42-row positive controls. Do not alter source physics or invent scientific compatibility.

## Current and untested consumer sources

| Consumer or entrypoint | Evidence | Treatment |
|---|---|---|
| New-only 42-row S6-417/941 | D10 exact Native P05; D12 matched control | **Supported / PASS** |
| Public D 100-row S6-417/941 | D11 actual generator PASS, D12 Native P2 FAIL | **Candidate supported / HOLD** |
| `ci/issue668_p2_newonly_stage_verify.py`, `ci/check_issue670_p4_x_full_newonly_runner.py` | Same 417/941 ownership staging family, not independent external Native coverage | Maintain scoped preflight, check route applicability |
| Issue402 `prepare_s6_run_input.py`, `prepare_s6_newonly.py`, `retire_s6_*_owners.py` | Current 417/941 source stage and P4-X evidence | Covered only for exercised cases |
| Issue402 `prepare_hybrid_json_s6.py` | Tracked callable, not independently designated supported New-only route | **Owner classification needed** |
| Issue395 `base14_restart_100to300us.py` and other old one-off workflows | Long-time-history/research route, different P3/P4 science | Separate science/owner disposition |
| Issue20 `thermal_gradient_activation/prepare.py` | `QPXFVThermalDiffusion` in separate `qpxApp` | **Separate application; do not edit** |
| Unknown third-party legacy `PhysicsFVThermalDiffusion` inputs | Requester waived current-binary compatibility | Explicit breaking change, **do not demand impossible unknown-caller-zero proof** |
| Known currently supported external integrations | No complete independent owner registry obtained | List by owner, replay contract or obtain explicit owner disposition |

A targeted GitHub code search on indexed **default-branch** content located the old PhysicsApp Factory files and historic FDEG references in this repository. This is **not** a global external-user inventory, does not cover private integration copies or all branches, and cannot serve as an external consumer-zero attestation.

## Precise release gates

1. **Owned supported generators:** review live entrypoints/Workflow callers, classify each `SUPPORTED`, `HISTORICAL`, `SEPARATE_APP` or `OWNER_DECISION`. Execute only supported routes with real output SHA + Native construction evidence. For unsupported old inputs, archive/deprecate rather than trying to keep Factory aliases alive.
2. **Known external supported integrations:** integration owners explicitly provide covered repository/consumer builds or state that the old typed input is no longer supported. Publish a breaking-change migration note. Unknown external legacy caller-zero is **not** a technical gate.
3. **Public D:** blocked specifically by current Native 100-row construction failure, independently of Thermal removal. Fix only with a classified MOOSE error and exact-head rerun.
4. **Final promotion:** exact combined integration SHA, production CI Workflow/template reconciliation, independent rollback/reviewer receipt and applicable P3/P4 scientific gates. No unreviewed Poisson change or `main` merge.

**Status: `D10_42ROW_NATIVE=PASS / D11_100ROW_GENERATION=PASS / D12_42ROW_CONTROLS=PASS / D12_100ROW_NATIVE=HOLD / EXTERNAL_SUPPORTED_OWNER_LIST=PENDING / SAFE_DELETE=HOLD`.** [Machine receipt](newonly_d12_public_d_native_hold_scope_v0_1.json).