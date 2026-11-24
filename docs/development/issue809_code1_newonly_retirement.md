# Code1 New-only source retirement — branch-stage evidence

**Issue:** #809, child of #774. **Base:** New-only D9 `87b7d97113ce6e75081dd15c56c86bc159bde6c9`.
**Status:** C/H SOURCE CUT APPLIED ON BRANCH / P0-P3 UNVERIFIED / MAIN_MERGE_HOLD.

## Exact scope
- Delete `physics_app/src/fvkernels/FVElectronResponseBandedCorrection.C` and `physics_app/include/fvkernels/FVElectronResponseBandedCorrection.h` together (Factory registration lives in the deleted C).
- Keep unrelated Poisson, electron energy, charge and transport owners.
- Update existing #774 New-only source/CI guard and existing Native Usage Census P0 tests to expect **11 C files / 16 local Factory types**, rather than 12/17. Both previously retired Thermal and code1 types must remain absent. Do not import legacy FDEG CI or add a new production CI job.
- Adopt the exact #706 `fdeg_historical_profiles_code1.json` archive without its stale CI template or PR-only one-shot Workflow.
- The original #351 historical generator `experiments/Issue351_frozen_heavy_driver_parity/control.py` is retained at immutable blob `6d7efcb4ea94b2011782aba2c9cab40238756312` and excluded *only by exact path and verified SHA* from active New-only token scanning. Other generated .py and .i consumers must still fail closed.

## Evidence distinctions
Historical #337/#351 qualified runs `36163219902` and `36496470116` both used the kernel. This history proves neither code1 OFF parity nor current-binary historical input support. Archive retains original C blob `1e58703a7794ddd8eed3cba28ed9e5a1e39a141f` and H blob `9446a9d5d7863fb83a2c65af8b127bbd08573ad6`.

The pre-delete 417/941 source census and D10 W1/Native P05 were on a **different SHA**; no P1/P2/P3 or deletion-scoped Native qualification may be transferred automatically.

## Pending acceptance and cleanup
1. P0 exact branch-HEAD source census, historical archive SHA, workflow/template consistency, negative mutation, active/indirect consumer guard, no unowned source references.
2. Clean P1 `physics-opt` rebuild and 417/941 Native P2/P05 + negative controls on exact post-cut SHA, protected EI data isolation.
3. Compare relevant output/regime for any claimed active semantic equivalence, otherwise explicitly bound to New-only no-code1-consumer scope.
4. Integration merge after Poisson ownership gate, exact CI/review, source rollback approval; remove inherited one-off Workflow YAML before main integration.
5. Close/annotate obsolete PRs and issue #809; update #774; delete safe isolated branches via Samuel exact-SHA provider; preserve historical GitHub Actions runs/artifacts. No irreversible Actions-history deletion.

**Not yet accepted:** `SAFE_DELETE=HOLD`, `SCIENCE_HOLD`, `MAIN_MERGE=DEFERRED`.
