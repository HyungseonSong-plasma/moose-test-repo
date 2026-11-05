# Oxygen ICP — Current research reaction base (2026-11-05)

**Authority label:** CURRENT_WORKING_REACTION_BASE  
**Scientific acceptance:** SCIENCE_HOLD — no production, original 25-channel registry, or rate-validation promotion.

## New pinned research BASE

- **Selected successful native run:** [Run #42049066748, run #1](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42049066748)
- **Exact run/source SHA:** `29d1acc6ef7969908b86719e4b95c73a1565136d`
- **Pinned source branch:** [base/oxygen-icp-14ch-ei941-ei412-ei401-ei415-20261105](https://github.com/HyungseonSong-plasma/moose-test-repo/tree/base/oxygen-icp-14ch-ei941-ei412-ei401-ei415-20261105)
- **Physics/MOOSE pinned source:** `8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab`
- **EEDF SHA-256:** `35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b`
- **Machine-readable authority:** [current_reaction_base.json](current_reaction_base.json), including verified artifact/inputs/run checksums and private-rate **hashes only**
- The GitHub branch is a **historical source locator**; exact SHA must be used for invariant replays.

## Exact ACTIVE chemistry (14 channels)

```text
EI-401  EI-02  EI-412  EI-415  EI-17  EI-941  EI-2738
EI-407  EI-417  EI-935  H24  H25  H23  EI-2069
```

**Four exclusive chemistry replacements** in this base:

| Removed legacy owner | ACTIVE replacement |
|---|---|
| EI-20 | **EI-941** |
| DISS-G | **EI-412** |
| EI-01 | **EI-401** |
| EI-16 | **EI-415** |

The replacements are **not parallel doubled rates**: the prior owner is removed from the actual solver reaction setup. EI-2069 and H23 remain ACTIVE; EI-943 and other excluded channels remain INACTIVE. This base **does not** include the separately launched EI-2069-OUT ablation study.

## Controlled predecessor and preserved historical base

- **Immediate one-channel A/B predecessor:** [Run #42047760912](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42047760912), EI-16 ACTIVE / EI-415 INACTIVE. The new selected run replaces **only EI-16 → EI-415** relative to this predecessor.
- **Prior working BASE (superseded as current, not erased):** [Run #42043664537](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42043664537), pinned commit `e2f2080649784a04f3300ea9dded1ae23b0a04b1` and historical branch [base/oxygen-icp-14ch-h23-ei941-20261105](https://github.com/HyungseonSong-plasma/moose-test-repo/tree/base/oxygen-icp-14ch-h23-ei941-20261105).
- **Frozen previous baseline contract:** [history/oxygen-icp-h23-no943-mcs2738-ei2069-ei941-14ch-20261105.json](history/oxygen-icp-h23-no943-mcs2738-ei2069-ei941-14ch-20261105.json). Historical provenance is not rewritten to pretend the new chemistry was previously in the base.

## Native validation and recovery assets

Both cases were started from fresh input; the 400 W and 1000 W native solves completed **P0–P4**, including the genuine 0–100 μs solver trajectory (460 steps, 461 time rows) and verified checkpoint.

| Metric | 400 W | 1000 W |
|---|---|---|
| P0–P4 | PASS | PASS |
| Full artifact ID | `13447489692` | `13448891366` |
| Native endpoint | 100 μs | 100 μs |
| Last RF power | 400.694485 W | 1001.020867 W |
| Native restart archive | SHA-256 pinned in JSON | SHA-256 pinned in JSON |
| Native input archive | SHA-256 pinned in JSON | SHA-256 pinned in JSON |

200 sccm neutral inlet, unchanged RF/mesh and EEDF, 460 native steps, and original unchanged remaining rates are part of this research comparison contract. **Private rate tables must not be published**; exact SHA-256 of each active lookup is recorded in the JSON.

## Rules for future controlled experiments

1. Start from **exact commit** `29d1acc6ef7969908b86719e4b95c73a1565136d`; no unreviewed experiment-branch head substitution.
2. Declare each change from the pinned 14 ACTIVE channels and perform an exclusive rate/source/energy-owner swap, no double-counting.
3. Reuse unchanged physical conditions, original unchanged source tables, RF/mesh, EEDF, inlet and timestep grid.
4. Start a **fresh solve**, never silently restart an incompatible chemistry checkpoint.
5. Require P0 source-provenance and rate-ownership checks, P1 genuine native build, P2 actual check-input, P3 true 100 μs solve, P4 checkpoint and recovery inventory.
6. Compare to both the current baseline and, where useful, the predecessor `#42047760912`, stating which chemistry dimension changed.

**Limits:** this is a **research reaction-channel working base only**, not a production-code promotion or science acceptance. [Issue #419](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/419) remains the authoritative original Oxygen25 reaction-identity registry. Source-identity uncertainties and SCIENCE_HOLD remain, including the EI-2738 MCS provisional mapping.
