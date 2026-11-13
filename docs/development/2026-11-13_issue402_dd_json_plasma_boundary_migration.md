# Issue #402 — JSON-owned DriftDiffusion plasma boundaries

**Status:** Draft branch `issue-402-dd-plasma-boundary-action`, stacked on Draft
PR #530. No merge, P3, powered ICP numerical parity, or SCIENCE acceptance.
**SCIENCE_HOLD**.

## Why the mean-energy Material still exists

For `state_form=log_molar_eV`, the solved states are real log molar
densities. The derived positive mean energy is
`exp(log_energy - log_ne)` [eV]. A log transformation excludes
nonpositive *represented physical states* for **finite, representable**
numerical values; it does **not** prevent nonfinite solver states, overflow
to infinity, or finite-precision underflow of the difference exponential
to zero. The existing `PhysicsElectronMeanEnergyMaterial` detects those
cases and refuses the invalid energy. For `physical_eV` and
`normalized`, density positivity and normalization also require
explicit validation. It remains live and differentiable; it is not a
setup-time constant. The optional `external` mean-energy ownership
preserves a preexisting validated provider without adding a duplicate.

## Why adjacent sheath wall flux still exists

`PhysicsElectronAdjacentSheathWallFluxMaterial` consumes live physical
electron density, mean electron energy and potential. Its wall-face
`FaceArg` evaluates plasma-adjacent `-grad(phi)`, normal direction,
wall-to-cell normal distance and the *same* positive outward electron
flux that the existing `FEMElectronSheathBC` and
`FEMElectronEnergySheathBC` consume. Existing particle/energy
sided-face and dielectric-current sign/ownership rules are unchanged.
It is **not** interchangeable with `PhysicsElectronWallFluxMaterial`
(thermal-only wall model), or a setup constant.

## Source-authoritative mesh names

Historical `experiments/Issue19_sccm_pressure_boundary/mesh.i` declares
plasma-facing `inlet`, `outlet`, `plasma_electrode`,
`plasma_metal`, `plasma_right`, `plasma_cover`,
`plasma_wafer`, `plasma_focus_ring`.
Historical Issue #395 electron wall uses all six named solid interfaces
and excludes inlet/outlet. These are **physical mesh sideset names**,
not a guarantee that every wall should share the same constitutive law.

**Suggested future scenario JSON** (with the actual mesh above):

```json
{
  "drift_diffusion_boundary": {
    "inlet":      {"mesh_boundary": "inlet",             "electron_model": "open"},
    "outlet":     {"mesh_boundary": "outlet",            "electron_model": "open"},
    "electrode":  {"mesh_boundary": "plasma_electrode",  "electron_model": "adjacent_sheath"},
    "metal":      {"mesh_boundary": "plasma_metal",      "electron_model": "adjacent_sheath"},
    "right_wall": {"mesh_boundary": "plasma_right",      "electron_model": "adjacent_sheath"},
    "cover":      {"mesh_boundary": "plasma_cover",      "electron_model": "adjacent_sheath"},
    "wafer":      {"mesh_boundary": "plasma_wafer",      "electron_model": "adjacent_sheath"},
    "focus_ring": {"mesh_boundary": "plasma_focus_ring", "electron_model": "adjacent_sheath"}
  }
}
```

This is **an illustrative migration contract**, not an assertion that
all six solid surfaces have passed physical wall-model parity.
For a wall still owned by an explicit special BC, set
`electron_model: "external"` in JSON. This prevents the generated
electron sheath BC on that surface. `open` and `external` do not
generate a new electron BC; they do **not** automatically create
inlet/outlet flow/charged-species/energy BCs or dielectric surface charge.

The new model enum is `open | adjacent_sheath | external`. The parser
fails on duplicates, unknown model, invalid alias, duplicate mesh
sideset, empty catalogue, multiple JSON catalogue owners, and a
literal `inlet`/`outlet` alias/sideset mapped to a solid sheath.

## New .i interface

```ini
[Physics]
  [Plasmas]
    files = plasma.json
    [Transport]
      [DriftDiffusion]
        plasma_boundary = json
      []
    []
  []
[]
```

The .i no longer repeats boundary names or their wall type. When
`plasma_boundary=none` (default), the Action creates nothing; existing
explicit `[FunctorMaterials]` / `[BCs]` remain the owner.
When `plasma_boundary=json`, Action obtains the **same shared**
`ChemistryData` instance from `PlasmasAction` and registers one
`PhysicsElectronMeanEnergyMaterial` (unless
`plasma_boundary_mean_energy_owner=external`), one
`PhysicsElectronAdjacentSheathWallFluxMaterial` (unless
`plasma_boundary_wall_flux_owner=external`) and **a pair of existing
FEM sheath BCs per `adjacent_sheath` mesh sideset**. They share the
same positive outward `electron_wall_number_flux`, and the energy
BC retains `Gamma/N_A * (5/2) * T_e`, with
`T_e = (2/3) mean_en_solved`. No new independent plasma boundary law.

To migrate an active .i, delete the paired explicit electron wall
`[BCs]` entries for those exact sidesets. Delete the previously
explicit mean-energy and adjacent-sheath wall Materials only if their
ownership has switched to `generated`. Use `external` owner options
for already validated existing providers. The current Action does not
detect arbitrary manually declared duplicate BCs; an **ownership
inventory** is still required before converting a production input.

The two synthetic P2 fixtures deliberately use 2D GeneratedMesh
standard sideset names: wafer -> left, cover -> bottom, inlet -> right,
outlet -> top; these names are NOT substitutes for the real production
mesh sidesets.

## Validation gates

- P0: schema/path/owner tests including invalid role and duplicate sideset;
- P1: native `physics-opt` application build;
- P2: actual `--check-input` positive generated and external mean-energy
  cases, plus negative malformed JSON/model/sideset/empty catalogue and
  missing JSON owner controls;
- P3: not run. In particular face-oriented flux, wall energy and charge
  conservation, and equivalence against full historical Issue #395 input
  are *not* established by construction checks.
