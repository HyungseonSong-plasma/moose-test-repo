# Issue #774 D7 — Legacy Thermal Factory binary A/B

> **Verified input-construction interface break. SAFE_DELETE=HOLD.**
> This deliberately synthetic input does **not** represent all historical workloads or scientific residual parity.

## Exact source/binary provenance

| Cohort | Git head | Existing W1 run | ELF SHA-256 |
|---|---|---|---|
| A (pre-source removal) | `6c4eef073038ad69a0710e7c8555b5e03b9ad6ba` | [#45177303119](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45177303119) | `6e0d04e48886a7897fa69aa85528c4aba41a9381451aa67f5477443c30df7f15` |
| B (post-source removal) | `c77d2f773eee96c30eeca49d7486fea22ea8e557` | [#45177755891](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45177755891) | `d6a87b61f7e3e8d06767f7a245c51e846293af740653609492d2e3f9714ac62c` |

Both reused one exact archived W1 per source SHA, with all ELF/app-library member SHA checks and identical OCI. No new PhysicsApp build, no protected rates, no Poisson changes.

## Native input/Factory construction result

- Test PR: [Draft #789](https://github.com/HyungseonSong-plasma/moose-test-repo/pull/789) exact HEAD `6c240d9f8b324d07b0e31eebaea1b9cbb60e8a6e`.
- Final actual run: [#45188611631](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45188611631) **SUCCESS**, public sanitized artifact #14824902064, ZIP SHA-256 `21845d2d48d736453862270ae6c5b57cd2c9fc56fa39b43ee16864633e164a2f`.
- Identical synthetic `.i` uses `type = PhysicsFVThermalDiffusion` and original `temperature`, `thermal_diffusion_coefficient`, `include_thermal_diffusion` API. Run twice, once with flag ON and once OFF. Deliberately missing Factory type is tested in both cohorts.

| Exact synthetic input | A (old Factory present) | B (after .C/.h removal) |
|---|---|---|
| Thermal `include_thermal_diffusion = true` | `--check-input` **Syntax OK**, rc=0 | `A 'PhysicsFVThermalDiffusion' is not a registered object.`, rc=1 |
| Thermal `include_thermal_diffusion = false` | **Syntax OK**, rc=0 | same missing-Factory error, rc=1 |
| Deliberately nonexisting `Issue774NonexistentKernelControl` | expected failure, rc=1 | expected failure, rc=1 |

**Verdict:** `FACTORY_INTERFACE_BREAK_CONFIRMED_IN_SYNTHETIC_INPUT`. Even with the Thermal flux disabled, removing the Factory makes the former type-name input invalid in the new binary. This is direct evidence of a *backward-compatible input interface loss*.

The first attempt [#45187995851](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/45187995851) remained HOLD because the safe log classifier omitted the MOOSE phrase `is not a registered object`. This was corrected with a unit test; the final success is only at the exact later head.

## Do not extrapolate

This is **not** confirmation that a particular historical archived `.i` ran unchanged, that any nonzero-temperature-gradient flux/AD residual agrees, or that a hidden/dynamic/third-party consumer exists or does not exist. D5's separate 417/941 40-FVKernel registration parity and D6's tracked-source scan remain valid but do not cancel this compatibility break.

## Gate decision (external authorization remains outstanding)

- **If the current PhysicsApp binary must still load old typed input:** **KEEP** the legacy Factory or provide a separately independently verified compatible alias/residual.
- **If this current-binary support is explicitly terminated:** require actual owner signoff, runnable pinned historical binary+input, external/generated scope disposition, and rollback/coverage/Native review before approving cutover.
- **Do not claim:** long P3/P4 or nonzero-gradient physical equivalence, independent rollback, or global caller-zero.

**`D7_SYNTHETIC_FACTORY_AB=PASS / CURRENT_BINARY_COMPATIBILITY=BREAK / OWNER_DECISION=HOLD / SAFE_DELETE=HOLD`.** Machine receipt: [JSON report](thermal_d7_legacy_binary_compatibility_v0_1.json).