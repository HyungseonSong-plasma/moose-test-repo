# Current oxygen ICP research reaction base — 2026-11-05

**Status:** CURRENT_WORKING_REACTION_BASE · **Science acceptance:** HOLD

**Machine-readable authority:** [current_reaction_base.json](current_reaction_base.json).
This is an experimental comparison base (known-good **native numerical replay**),
**not** a production/physical-chemistry validation and **not** a change to the
[Issue #419 original Oxygen25 reaction registry](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/419).

## Selected immutable reference

- **Selected:** [Actions Run #42043664537, run #5](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42043664537), source commit
  e2f2080649784a04f3300ea9dded1ae23b0a04b1.
- **Pinned base code branch:** [base/oxygen-icp-14ch-h23-ei941-20261105](https://github.com/HyungseonSong-plasma/moose-test-repo/tree/base/oxygen-icp-14ch-h23-ei941-20261105).
  It was created **at the exact verified run commit**. Any future movement of the
  branch is not proof of replay; for immutable replays use the SHA.
- **Physics source:** 8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab.
- **Initial EEDF transport SHA-256:**
  35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b.
- **Predecessor for A/B:** [Run #41994865552](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/41994865552)
  (EI-20); the selected base performs the **exclusive EI-20 → EI-941** replacement.
- The original research workflow filename contains “13ch” because of its
  historical origin; **this selected successful run is explicitly 14ch**.
  Identify cases by the verified run ID and 14-channel manifest, not that name.

## ACTIVE channels (14)

| Type | Exact IDs |
|---|---|
| Legacy backbone | EI-01, EI-02, DISS-G, EI-16, EI-17 |
| Original HPEM electron channels | EI-941, EI-2738, EI-407, EI-417, EI-935, EI-2069 |
| Heavy reactions | H24, H25, H23 |

**Excluded from this specific base:** EI-20 (replaced), EI-943,
EI-2058, EI-2259, H05, EI-2072, EI-2074.
This is **not** an assertion that the other Oxygen25 reactions have been
accepted or individually evaluated. EI-2069 is **ACTIVE** here.

**Explicitly NOT included:** later EI-401 for EI-01, EI-412 for
DISS-G, and EI-415 for EI-16 replacement experiments; and the
separately launched EI-2069-out 13-channel ablation. These remain research
**descendants / candidates**, not silent modifications to this base.

## Evidence and conditions

Both powers were prepared from **fresh input** with 200 sccm inlet, same
RF/mesh and fixed EEDF; both completed P0–P4, including a true **0–100 μs**
native solve and **460 native steps**, 461 time rows, with verified full
checkpoint and restart evidence:

|  | 400 W | 1000 W |
|---|---|---|
| Native job | P0–P4 PASS | P0–P4 PASS |
| Full result artifact ID | 13445953720 | 13446601738 |
| Final native time | 100 μs | 100 μs |
| Final RF power in manifest | 400.61210319789 W | 1000.8756884399 W |

Full artifact SHA-256, native-run archive SHA-256, input archive SHA-256,
private rate **checksums only**, and exact reaction inventory are in
[current_reaction_base.json](current_reaction_base.json). Do **not** commit
private rate files or treat public hash references as substitute for
the source rate package.

## How new reaction experiments use this base

1. Start from **exact commit** e2f2080649784a04f3300ea9dded1ae23b0a04b1
   (or use the named base branch only if it still points to that commit).
2. Declare the single intended channel addition/removal/replacement. Do not
   inherit changes from an unrelated experiment branch.
3. Preserve all other source/lookup hashes, RF Maxwell settings, inlet,
   mesh, initial conditions and EEDF, time grid, diagnostics and scientific
   HOLD. A **fresh** state is required when chemistry differs; do not resume
   an incompatible checkpoint.
4. Run **P0 inventory and provenance, P1 native compilation, P2 solver
   check-input, P3 real 100 μs integration, P4 real checkpoint validation**.
5. Report separate numerical differences and physical acceptance. A
   successful CI run does not establish cross-section validity, reaction
   branching, EI-2738 MCS reaction identity, or other scientific HOLDs.

### Promotion boundary

This is a **reaction-channel working base selection only**. No production
MOOSE Physics chemistry owner has been replaced, Issue #419's reaction
identity authority is unchanged, and no science HOLD is lifted. Production
canonical promotion requires the owning issue's scientific evidence and
appropriate independent review/approval.
