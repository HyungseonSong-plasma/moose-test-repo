# #774 D14 — Public D original 100-row Native P2 417/941 PASS

> **Tested source contract: PASS, real `physics-opt --check-input` for both cases.** Original old typed `PhysicsFVThermalDiffusion` input support is explicitly waived. This result does not assert long 100 µs scientific parity, outside-repository caller-zero, or permission to merge to `main`.

## Immutable proof

- Tested [Draft #804](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/804) exact code HEAD `581bdd03a6ab2e09c841903a6ac1761b54793753`; Git tree `dc51c87097bec3335f78119c1d34c3ffaef57b25`.
- [GitHub Actions run #45215687714](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45215687714): **SUCCESS**, sanitized Artifact **#14838747216**, ZIP SHA-256 `4cfb7ce86168c86bb496b8ce98d5ef27af42c04da00fa990cdeeec0e88beef49`.
- Same exact previous D10 W1 PhysicsApp ELF `6afd05d4a4d356fe5132ca28076ba27e06bea93d485ac8a6b39d334bb9a9465b`, with its two SHA-checked application libraries and pinned OCI, **not rebuilt**.
- Real original protected EI rates were staged only in 0700 private scratch with 0600 files. `protected_rate_cleanup_verified=true`; `protected_data_in_artifacts=false`; no private Native logs uploaded.

## All four actual Native configurations

| `physics-opt --check-input` | S6-417 | S6-941 |
|---|---|---|
| Original 42-row New-only | **rc0 / Syntax OK** | **rc0 / Syntax OK** |
| Original Public D 100-row electron table only | **rc0 / Syntax OK** | **rc0 / Syntax OK** |
| Public D Chemistry JSON/overlay binding only, original table | **rc0 / Syntax OK** | **rc0 / Syntax OK** |
| **Full generated Public D 100-row** | **rc0 / Syntax OK** | **rc0 / Syntax OK** |

Both cases prove the complete composed public staging retained **22/22 original public files**, changed exactly **2** intended existing files (electron transport table and `migrated_continuity.i`), added exactly **1** generated `public_d_s6_{case}_physics.json`, and preserved every other original support SHA. The synthetic regression control rejects removal of any unrelated public support file.

## What was actually wrong in D12/D13

D11 generated correct public 100-row table, JSON, and 11-layer inputs, but the first D12/D13 Native harness copied the **generator's minimal experiment output directory** as if it were the **complete P3-X case worktree**. Other Native controls copied the complete original staged worktree. Their input file footprints differed beyond the two intended factors, so D13's `TABLE_AND_JSON_INTERACTION` diagnostic label could not support a causal conclusion. D14 corrected the comparison by composing generated changes onto the *complete* P3-X public staged worktree, as the canonical `.github/workflows/ci.yml` already intends to do.

After the staging repair, all eight actual Native checks succeed without changing Physics C++, chemistry generator policy, original 100-row data, or restoring the retired Thermal Factory. The previous D12 error is therefore attributable to test-harness staging incompleteness in the exercised runs, **not evidence of broken ThermalDiffusion source retirement**.

## Internal/external boundaries and release gates

- **Repository-internal sources:** `.github/workflows/ci.yml` owns actual New-only Public D generation; S6 P4-X is a scoped helper. Issue402 Hybrid and Issue541 ARCH replay are separate pinned experiments. Issue395 100-to-300 µs restart is separately reviewed science; `QPXFVThermalDiffusion` belongs to another Application.
- **External consumers:** requester reports they generally do not exist. Record `NONE_REPORTED` (not a mathematical proof of zero), waive unknown-global-caller search and third-party approval as a release gate. If an actual supported external integration is later identified, review only that integration.
- **Current P0/P2 coverage:** historical D8 FDEG CI PASS, New-only D9 CI PASS, New-only D10 actual 42-row W1/P05 PASS, D11 generated Public D 100-row PASS, and **D14 Native Public D 100-row P2 PASS**.
- **Not established:** long P3/P4/100 µs physical conservation and semantic compatibility; independent code-owner and production rollback approval; final combined exact `main` integration SHA and the concurrent Poisson work.
- **Production CI hygiene:** D13/D14 are *one-off verification Workflows* and should be dropped from the final production CI tree while preserving the immutable runs. Do not transplant the old historical FDEG Workflow into New-only.

**Verdict: `D14_PUBLIC_D_417_941_NATIVE_P2=PASS / INTERNAL_SOURCE_SCOPE=PASS_FOR_EXERCISED_ROUTES / EXTERNAL_INTEGRATIONS=NONE_REPORTED_NOT_A_GATE / SAFE_DELETE=HOLD_FINAL_INTEGRATION_REVIEW / MAIN_MERGE=DEFERRED`.**

[Machine-readable receipt](newonly_d14_public_d_native_p2_pass_v0_1.json).