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
