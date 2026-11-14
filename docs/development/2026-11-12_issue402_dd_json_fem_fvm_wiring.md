## JSON-driven FEM/FVM DriftDiffusion ownership (Issue #402)

In `[Physics]/[Plasmas]/[Transport]/[DriftDiffusion]/[Continuity]`,
`fem_species` and `fvm_species` select **exactly** the species for which
`DDContinuityEq::addFunctorMaterials()` instantiates `DDMaterial`.
`PlasmasAction` merges the ordered JSON files and validates coefficient
records (including duplicate owner conflicts and charge/species identities).
The C++ provider names are always `<species>_mobility` [m²/(V s)] and
`<species>_diffusivity` [m²/s]; no per-species `[FunctorMaterials]`
declaration is needed.

Per species, `transport_coefficients.drift_diffusion` accepts:

- `{"model":"constant","mobility":0.25,"diffusivity":0.125}`
  with finite, nonnegative physical coefficients
- `{"model":"lookup","table_file":"tables/e.txt",
  "table_units":"reduced","pressure":"p","gas_temperature":"T_g",
  "bounds_policy":"error"}` — table columns
  `coordinate mobility diffusivity`, reduced by `N_n = p/(k_B T_g)`
- `{"model":"lookup","table_file":"tables/ion.txt",
  "table_units":"physical"}` — values are already physical
- `{"model":"functor"}` — existing species-named AD Functors,
  `<species>_mobility` and `<species>_diffusivity`; no JSON source overrides

Relative `table_file` paths resolve relative to the JSON declaring them,
not to the working directory or `.i`. Every table has at least two rows,
strictly increasing **finite** coordinates and **finite nonnegative**
coefficient columns. Out-of-range coordinates error by default; explicit
`bounds_policy=clamp` is allowed.

No front-end toggle is used. When the merged JSON declares any
`transport_coefficients.drift_diffusion` species, every selected FEM/FVM
species must have a JSON DD record. Partial records fail before a solver step.
When the DD section is completely absent, historical Native coefficients
remain owned by Native S6 Materials without invented lookup values or constants.
The JSON species list does not by itself trigger Material construction:
only the Continuity FEM/FVM selection does.

Test-only standalone input:
`experiments/Issue402_plasma_dsl_g1/valid_json_dd_fem_fvm_mixed_p2.i`
references `json_dd_fem_fvm_mixed_p2.json`: e uses the provisional
`chemistry/e_transport.txt` reduced table,
Om uses a physical table, O2p and Op constants. All coefficients, rate
state and thermal coordinate values are synthetic P2 fixtures, NOT validated
S6 physical values.

**Scope boundary:** both FEM and FV species receive coefficient Functors.
The current `DDContinuityEq` creates FEM drift-diffusion Kernels only;
ion FV transport Kernels are still Native-owned and must explicitly consume
the canonical coefficient Functors if this JSON cutover is activated.
No B/C historical archive changes, production P3 run, merge or
scientific parity acceptance are implied. `SCIENCE_HOLD`.

The lookup coordinate Functor is implicitly `mean_en_solved`,
not configured per species in JSON. Electron energy transport is a
separate `e_energy: {"type":"fluid"}` selector, using 5/3 times
the electron particle mobility and diffusivity. The reference
`e_transport.txt` remains synthetic and not science-qualified.
