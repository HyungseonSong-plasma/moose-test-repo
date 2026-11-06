# Issue #395 — powered oxygen ICP chemistry activation ladder


## Issue #457 — C0-400 chemistry-OFF electron-profile discriminator (implementation P0 only)

- Owner: [Physics #457](https://github.com/HyungseonSong-plasma/moose-test-repo/issues/457).
- Immutable research control: Oxygen14 source `29d1acc6ef7969908b86719e4b95c73a1565136d`; associated native Physics source `8e2fe042dbc204b5fda22d346f1ad8d2e32db3ab`. Historical 14-channel 400 W P3 control: [Run #42049066748](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42049066748).
- **Intent:** fresh 400 W, 0–100 µs 460-step run with no volumetric or chemically reactive wall source, preserving existing RF/Poisson/electron transport and charged wall loss. This is a *diagnostic*, not a physically self-sustaining plasma model; electron density decay is expected when ionization is suppressed.
- **Current deliverable:** fail-closed candidate manifest and 2D native Exodus profile observation, **not an actual executable approved Chemistry-OFF input**. The operator must restore the archived pinned source and original private data through authorized channels; never put private rate tables in repository artifacts.

After preparing the historical Oxygen14 400 W input and RF parent overlay in an **independent exact-SHA source checkout**, run the branch-provided canonical CLI code with explicit absolute paths to that checkout:

```bash
python3 bin/physics.py oxygen-c0 \
  --root /path/to/pinned-oxygen14-checkout \
  --base-input /path/to/pinned-oxygen14-checkout/experiments/Issue395_powered_chemistry_ladder/rf_elastic_diss_ion_ei20_ei01_400w_adjacent_sheath_wall_closed_100us_dt1000ns.i \
  --rf-parent /path/to/pinned-oxygen14-checkout/experiments/Issue395_powered_chemistry_ladder/rf_elastic_multiapp_parent_400w_100us_dt1000ns_overlay.i \
  --output /path/to/pinned-oxygen14-checkout/experiments/Issue395_powered_chemistry_ladder/c0_400_evidence/manifest.json
```

This only emits **candidate** `check_argv` / `solve_argv`; it does not run them. All reaction overlays are omitted from that proposed invocation. Nested included files are scanned for known source signatures and reactive wall terms; if the original base still embeds chemistry, the command is designed to HOLD. The P0 string inventory is explicitly not an exhaustive MOOSE object/residual audit. No P2/P3 execution should be launched solely because this command returned zero.

After **separately authorized, exact-application** P1/P2/P3 native validation produces a genuine `plasma.e` (and all source/manifest audits pass), the observation-only extractor is:

```bash
python3 bin/physics.py oxygen-profile \
  --exodus /path/to/plasma.e \
  --c0-manifest /path/to/c0_400_evidence/manifest.json \
  --output-dir /path/to/new-profile-evidence-directory
```

It requires the exact 461-point native time grid, named `plasma` Exodus block, nodal `log_ne` and `log_energy`, and outputs `electron_profile_2d.csv` / `profile_summary.json` for 0, 0.1, 1, 2, 10, 25, 50, 75, 100 µs. Conversion: `n_e [m^-3] = N_A exp(log_ne)`, `mean_energy [eV] = exp(log_energy-log_ne)`, `T_e [eV] = 2/3 mean_energy`. Native output/provenance identity must be independently checked against the C0 run, not merely the filename.

**Hold gates:** complete direct/transitive chemistry and wall owner census; independently verified unchanged transport/RF/mesh/walls and valid 400 W target; real native P2; 0–100 µs P3; spatial electron shape and RZ charge/energy accounting; THEN compare against 14-channel baseline. Neither static tests nor profile extraction alone can establish scientific acceptance.


## Current research reaction-channel base (2026-11-05)

The **CURRENT_WORKING_REACTION_BASE** for 400/1000 W oxygen ICP research
experiments is now **[Run #42049066748](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/42049066748)**,
with 14 ACTIVE channels and verified fresh 0–100 μs native P0–P4 PASS.
Source SHA: `29d1acc6ef7969908b86719e4b95c73a1565136d`.

Active replacement reactions **EI-941 / EI-412 / EI-401 / EI-415** explicitly
replace **EI-20 / DISS-G / EI-01 / EI-16** (respectively), not run in
parallel. H23 and EI-2069 remain ACTIVE; EI-943 remains excluded.

- [Machine-readable BASE and artifact/rate hashes](research_baselines/current_reaction_base.json)
- [Research BASE replay and authority boundary](research_baselines/README.md)
- [Preserved historical EI941-only BASE](research_baselines/history/oxygen-icp-h23-no943-mcs2738-ei2069-ei941-14ch-20261105.json):
  previous Run #42043664537, source `e2f2080649784a04f3300ea9dded1ae23b0a04b1`.

**Boundary:** BASE is a **research reaction-channel numerical comparison
reference only**; SCIENCE_HOLD persists. It is independent of the Issue #397
mesh baseline below, does **not** rewrite the Issue #419 original Oxygen25
reaction identity registry, and does **not** contain the separate EI-2069-OUT
ablation candidate.

## Issue #397 200 W EI17 mesh baseline (2026-10-21)

**ACTIVE WORKING BASELINE: Graded Coarse L1**, not original pre-local-2x,
graded L2/L3, refined r≤20 mm L1, or the later R-only/Z-only preview meshes.
This selection applies to **future Issue #397 200 W EI17 comparisons only**;
it does not supersede the Issue #376 / #395 historical accepted physics inputs.

- Canonical mesh: 1,739 nodes, 3,155 2D triangles, **27 wafer faces**,
  max center wafer face 8.70967742 mm, restored outer face 4.35483871 mm.
- Verified mesh SHA-256:
  `ac70642df75bf7b4bc4ec0d92511e545f0942f9e07a1361618fb9eb5696b83fc`.
- Original source mesh SHA-256:
  `91299b6fc16136dfc9c4426148113b07ddfd7e95839da7abf5f14c36a4eac9cf`.
- Manifest: `issue397_baseline_mesh.json`. Generator:
  `issue397_build_graded_mesh.py`, plus same-directory geometry/quality modules.
- Validated run: [GitHub Actions #39575896519](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/39575896519),
  L1 job 100 μs physical solve and native D1 charge/current conservation PASS;
  evidence artifact `issue397-pre2x-graded-coarse-L1-100us-evidence`.
- This is a **mesh baseline selection, not proof that electron-density
  defects have been eliminated**.

**Prepare mesh for a new controlled run:** after generating the *original*
dielectric multi-material Gmsh file, replace the Issue395 simulation mesh
target with this command:

```bash
CHEM=experiments/Issue395_powered_chemistry_ladder
DIEL=experiments/Issue3_dielectric_surface_charge
python3 "$CHEM/issue397_materialize_l1_baseline.py" \
  "$DIEL/baseline_plasma_plus_unstructured_cover_plus_wafer.msh" \
  "$CHEM/baseline_plasma_plus_unstructured_cover_plus_wafer.msh"
```

This selector independently checks exact source mesh, generated mesh,
wafer interface plasma-side ownership, node/triangle/face counts and physical
group identity; a mismatch is a hard failure. Do not run the legacy local
2× refinement or uniform radial coarsening **after** materializing the
baseline. Validate an archived L1 `.msh` without regeneration using
`--verify-existing path/to/file.msh`. Keep original 200W EI17
thermal+migration ion wall conditions and existing electron sheath for
apples-to-apples experiments.

## Ground-state O2 dissociation rate correction (bounded successor, 2026-10-26)

The canonical generator `build_o2_dissociation_overlay.py` now targets **only**
`e + O2(X) -> e + O(3P) + O(3P)`. This is a new source change, not a
reinterpretation of the historical Issue #397/#403 graded-L1/EI17 results or
their recorded provenance.

- **Reaction-rate fit:** Zhao et al., *Physics of Plasmas* **31**, 083507
  (2024), [Table I (4)](https://doi.org/10.1063/5.0214357),
  `k_num = 1.41e-15 * Te^(-0.22) * exp(-2.98/Te) [m3/s]`;
  `Te = (2/3) * mean_en_solved [eV]`. The `2.98` eV scale is an
  **empirical rate-fit parameter, not an electron-collision threshold**.
- **Electron energy loss:** `6.0 eV/event` is the explicitly selected
  *effective* ground-state dissociation loss from the
  [COMSOL Ar/O2 ICP example, Table 2 (13)](https://doc.comsol.com/6.4/doc/com.comsol.help.models.plasma.icp_argon_oxygen/icp_argon_oxygen.html).
  It differs from the thermochemical ground-state O2 dissociation limit
  (~5.12 eV) and must not be mislabeled as that limit. The fit and
  energy-loss convention are separately sourced.
- **Projections:** unchanged single molar progress `R_diss_O2`,
  oxygen-mass gain `+0.032 R`, implicit O2 loss `-0.032 R`,
  energy source `-6.0 R`, and zero net electron-particle source.
  The electronic-excited O(1D) channel is **not activated**.
- **Validation:** `tests/test_o2_ground_state_dissociation_overlay.py`
  provides a generated-input regression and independent numeric rate anchors
  at 2 and 4 eV, source/energy closure and fail-closed negative cases.
  Repository CI is construction/static evidence only. Before promoting this
  change into an accepted powered ICP baseline, require a separately scoped
  real `physics-opt` P2/P3 and scientific source/energy/power/convergence
  comparison against the previously pinned 100-us control. No historical
  run, mesh, solver, wall condition or study record is rewritten.

## 2026-10-26 P2 construction repair / independent retry

[Initial ground-state tri-power run #40295762963](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40295762963)
failed at real `physics-opt --check-input` for **all 200, 600 and 1000 W**:
`PhysicsFEMLogMolarElectronFieldLimitedFluxBC` was not registered.
The original `P0` Python generator and `P1` C++ build passed, but both
electron particle/energy `FieldLimitedFluxBC` class names in the generated
input had no PhysicsApp implementation. No time-integrated P3 physics result
was produced; the P5 missing-data verdicts were downstream consequences.

The repair introduces both **registered FEM log-molar BCs**, using
`electron_wall_number_flux` from the existing
`PhysicsElectronAdjacentSheathWallFluxMaterial` via a **plasma-sided FaceArg**.
This is the same wall-flux functor/side policy used by the charge/current
ledger. The particle residual converts number flux to molar flux via
`N_A`; the energy residual consumes the same particle flux times
`5/2 T_e` with `T_e=(2/3) mean_energy`. Both skip the non-plasma side of
internal dielectric sidesets. It is deliberately **not** a thermal-only
`ElemQpArg` evaluation, which would bypass the intended sheath suppression.
No wall, mesh, RF, Maxwell, chemistry or PID target model is changed.

The one-shot workflow self-path is touched only to launch an independent
new SHA-locked 200/600/1000 W retry after PR checks. The new P0 regression
requires both C++ registrations, one-sided face evaluation and shared-flux
energy/particle ownership. A real `physics-opt` P2 is still mandatory before
starting P3. Do not count the first attempt as scientific failure or reinterpret
old accepted 100-us simulations.

## Original Issue #395 scope

This experiment surface grafts the accepted Stage-5 S5-R oxygen chemistry onto the merged Issue #376 1000 W RF baseline **incrementally**.

## Policy

Do not turn on the full chemistry ledger at once. Promotion is monotonic and gated:

- A0: chemistry OFF regression on the #376 powered baseline.
- A1: EI02 + EI16 only.
- A2: add EI01.
- A3: add EDETACH_OM.
- A4: add EI10.
- A5: add EI17 + EI19 + EI18 + EI20.
- A6: add H01.
- A7: add H02 + H03 + H04.
- A8: add H05; this equals the complete currently admitted S5-R-v1 14-channel set.

The activation inventory is machine-readable in `chemistry_sets.json` and checked by `check_chemistry_sets.py` against the frozen S5-R contract.

## Initial work package

Only A0 and A1 are authorized for the first runtime discriminator.

A1 is deliberately the minimum powered sustaining chemistry:

```text
EI02: e + O2 -> e + O2
      elastic electron-heavy energy exchange

EI16: e + O2 -> 2e + O2+
      O2 ionization + electron production + 12.06 eV electron-energy loss
```

The intended feedback chain is

```text
1000 W RF heating
  -> mean electron energy
  -> EI02 cooling + EI16 ionization
  -> electron / O2+ state
  -> plasma conductivity
  -> Maxwell
  -> RF heating
```

## State representation bridge

The powered production state from #376 is FEM log-state. Chemistry must consume physical quantities derived from that state:

```text
n_e [1/m3]     = N_A * exp(log_ne)
mean_en [eV]   = exp(log_energy - log_ne)
```

No second electron density or electron-energy state is permitted.

## Ownership invariants

The accepted S5-R rules remain binding:

1. exactly one canonical molar reaction progress per active reaction;
2. downstream heavy/electron/electron-energy projections reuse that progress;
3. no duplicate kinetic re-evaluation;
4. strict electron-impact lookup bounds;
5. no synthetic rate data;
6. blocked O2 dissociation channels remain disabled;
7. RF heating and electrostatic electron work remain separate owners.

## A0/A1 acceptance

Before A2 is eligible, establish on exact-head real `physics-opt`:

- A0 reproduces the #376 powered baseline within declared numerical tolerances;
- A1 activation inventory is exactly `{EI02, EI16}`;
- source ownership and reaction progress are unique;
- heavy mass / oxygen nuclei / electron-inclusive charge bookkeeping closes;
- EI16 electron particle and 12.06 eV energy projections consume the same progress;
- EI02 contributes energy exchange only and does not change species inventories;
- electron state remains finite and positive;
- mean-energy lookups remain in strict table range;
- RF absorbed/deposited power closure remains valid;
- reaction-rate/source extrema are recorded before expanding the network.

## Upstream authorities

- powered RF baseline: Issue #376 / PR #394;
- chemistry ownership: Issue #176 and `docs/development/2026-09-11_issue192_stage5_s5r_representative_contract.json`;
- integrated wall/SEE/chemistry compatibility history: Issue #27.
