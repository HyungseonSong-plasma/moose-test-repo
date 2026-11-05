# PREPARED ONLY — 13-channel H23 IN / EI-943 OUT

Status: **READY FOR FUTURE AUTHORIZATION; NOT LAUNCHED.**

## Scope
- Fresh MOOSE plasma simulation for **400 W and 1000 W**, **0–100 µs** in the original 100-us timestep grid.
- H23-inclusive parent model: 14 channels from the earlier H23 run.
- Remove **only EI-943**: e + O(1D) -> e + O(3P), including its private-rate lookup, both atomic-O species source kernels, and the +1.967 eV electron-energy source kernel.
- Keep exactly these **13 active** channels (order preserved):
  1. EI-01
  2. EI-02
  3. DISS-G
  4. EI-16
  5. EI-17
  6. EI-20
  7. EI-2738
  8. EI-407
  9. EI-417
  10. EI-935
  11. H24
  12. H25
  13. H23
- Preserve prior IMPACT_HOLD exclusions: EI-2259, EI-2058, H05, EI-2072, EI-2074; EI-936 and EI-2067 remain unenabled. No H23 removal.

## Fixed physics and controls
- Pinned original Physics source: `8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab`.
- EEDF lookup SHA256: `35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b`.
- Original EI-2738 formula, EI-407/EI-417/EI-935 private rates, H23/H24/H25 heavy chemistry.
- Same RF Maxwell coupling, gas inlet and initial-state recipe; 200 sccm original inlet.
- Both cases start from fresh initialization at t=0 (not 40µs restart).
- All results remain `SCIENCE_HOLD` even if numerical execution succeeds.

## Prepared implementation
- `.github/scripts/oxygen_h23_no_ei943_13ch_100us.py`:
  - `self-test`, `prepare`, `verify`, `archive`.
  - Derive original exact 14ch model from H23 parent, then remove EI943 from **both check and solve** argv.
  - Remove working-copy EI943 overlay and private lookup (without deleting the original protected rate bundle).
  - Independently validate 13ch inventory, H23 inclusion, other lookup SHA, native inputs, endpoint and restart archive.
- `.github/workflows/oxygen-h23-no-ei943-13ch-400-1000w-100us.yml`:
  - 400/1000W matrix, P0–P4 validation, 100µs checkpoint and diagnostics.

## Launch interlock — IMPORTANT
**DO NOT create** `experiments/Issue395_powered_chemistry_ladder/PREPARED_H23_NO_EI943_13CH_LAUNCH.run` until the user separately orders the actual run.

- Workflow push triggering is restricted to this specific preparation branch *and* that exact absent marker path.
- The workflow also advertises `workflow_dispatch`, which must not be invoked without separate authorization.
- Merely committing the preparation script, workflow or this specification must not launch the native simulation.
- Future explicit authorization is required to add the marker / dispatch and run both jobs.
- No GitHub Actions P0/P1/P2/P3/P4 validation has yet been executed for this new variant.

## Comparison references
- H23-IN / EI943-IN 400W: existing 14-channel H23 reference, Run 41806277977 (use verified 400W job).
- H23-IN / EI943-IN 1000W: Run 41857047208 40us + resumed 41928440328 40→100us.
- H23-OUT / EI943-OUT 12ch control exists separately: Run 41883786886 (already succeeded). **This is a different control and must not be conflated with this H23-IN / EI943-OUT 13ch variant.**
