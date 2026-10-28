# Issue #395 — powered oxygen ICP chemistry activation ladder

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


## Experimental mixed-state O2 dissociation (O(3P) + O(1D))

**Status: experimental / source-EEDF parity HOLD; not enabled by default.**

Add a *separate* O2 product-state channel to the existing canonical generator:

`python3 experiments/Issue395_powered_chemistry_ladder/build_o2_dissociation_overlay.py --base-input <generated_base.i> --output <mixed_overlay.i> --channel mixed`

Reaction: `e + O2(X) -> e + O(3P) + O(1D)`.
The existing `w_O` is O(3P), the existing `w_Os` is O(1D).
**No new species or initial-condition default is introduced.** The old
`--channel ground` (default) remains unchanged and generates only
`e + O2 -> e + 2O(3P)`.

Single progress `R_diss_O2_mixed` [mol/(m3 s)] owns:
- `+0.016 R` [kg/(m3 s)] for O(3P) solved FV variable;
- `+0.016 R` for O(1D) solved FV variable;
- `-0.032 R` implicit constrained molecular O2 mass loss;
- `-8.4 R` electron-energy sink, 8.4 eV/event COMSOL ICP Table 2 (14);
- zero net electron particle source and identically zero heavy/oxygen mass defect.

The provisional Maxwellian fit is
`k_num = 3.49e-14 exp(-5.92/Te[eV]) m3/s`;
`Te[eV] = (2/3) mean_en_solved[eV]`.
It is the fit used for an EEPF/temperature-model comparison in
[Excitation Kinetics of Oxygen O(1D) State in Low-Pressure Oxygen Plasma (2017)](https://doi.org/10.1515/jaots-2017-0002).
Do not misattribute the fit or call the fit scale a collision threshold.
The electron loss 8.4 eV/event comes from the
[COMSOL ICP oxygen reaction table](https://doc.comsol.com/6.4/doc/com.comsol.help.models.plasma.icp_argon_oxygen/icp_argon_oxygen.html).
**A fitted rate coefficient is not a source-verified independent
state-resolved cross section.** A separate source/cross-section/EEPF audit is
needed before interpreting the mixed and ground channels as exclusive.

`tests/test_o2_mixed_state_dissociation_overlay.py`
checks independent numeric anchors, exact 1:1 O(3P)/O(1D)
product stoichiometry, constrained O2 and electron energy,
no new species, and negative mutation controls.
No P2 physics-opt or P3 100-us production-path result has been asserted.
The model's volumetric O(1D) quenching/return-to-O(3P) coverage must be
audited before claiming credible O(1D) density or O(3P) response.

### 400/1000 W mixed-only DISS replacement (independent two-arm experiment)

User-selected controlled comparison: at 400 W and 1000 W, **switch the
single active electron-impact O2 dissociation slot from**
`e + O2 -> e + 2O(3P)` **to**
`e + O2 -> e + O(3P) + O(1D)`. Do not enable both.

The canonical `issue397_l1_power_scan_replay.sh` now accepts
`DISS_CHANNEL=ground` (default, unchanged) or
`DISS_CHANNEL=mixed` (new). Examples:

```bash
export DISS_CHANNEL=mixed
bash experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh prepare 400
bash experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh build 400
bash experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh check 400
bash experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh solve 400
bash experiments/Issue395_powered_chemistry_ladder/issue397_l1_power_scan_replay.sh audit 400
```

Repeat for 1000 W from a separate independent checkout. Source inputs use the
successful **nonzero initial O** composition, untouched sheath/walls, identical
Graded L1/27 wafer-face mesh, PID and 460-step 100-us time grid; only the
chosen dissociation overlay changes. The output directory gets the suffix
`_mixed_o3p_o1d` to prevent confusion with historical ground-state data.

For new channels the generated DISS overlay owns one and only one
`R_diss_O2_mixed` with `+0.016R` O(3P),
`+0.016R` O(1D), `-0.032R` constrained O2 mass, and
`-8.4R` electron energy. The generated base input must
not define a second ground-state dissociation owner.
P0 guards check exact owner names (not substring matching),
the two independently solved product variables, numeric rates, and
mass/oxygen/electron-energy invariants.
P5 reuses `analyze_ground_state_power_scan.py --channel mixed` for
O/Os creation/consumption, RF power and native D1.

**Science HOLD:** This is a model-regime change, not a power-only comparison.
The O(1D) quenching and electronic-state kinetics are not yet source-complete;
the Maxwellian rate fit is not independently cross-section/EEDF validated.
The numerical result must not be promoted to a chemically validated
prediction solely because the job succeeds.

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
