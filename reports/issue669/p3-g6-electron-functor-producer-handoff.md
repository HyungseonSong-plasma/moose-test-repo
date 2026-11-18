# P3-G6 — exact source Functor lineage and P3-X handoff

**Verdict:** `PASS_SOURCE_BYTES_AND_CPP_PRODUCER_CONTRACT / HOLD_NEWONLY_NATIVE_WAREHOUSE`.

Latest checked Draft PR #665 HEAD: `b5c1de717bd944bfa11685e826a922fbb6ae483a`. Existing pinned CI [run 44201394393](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44201394393), artifact #14381456912 SHA256 `5497c80badab09d7d3266a4c81e2a5d2272a1c9cc216e94e192c8ec1ecd78e95`. 417/941 staged 11/11 file SHA, JSON and historical 42-row table `35534a522fa48ccb5222339c5040040630eef31e623e1c53f1e1c4540d2d653b` rechecked independently.

## Pinned C0 direct Functor owners (both cases)

| Object | Emitted Functor | Raw block SHA256 | P3-X action |
|---|---|---|---|
| `electron_molar_density` | `electron_molar_density` | `d62268f610d606b407c0e042162bdd490dd86b4cd3d1a6dbb8fd57070acafe2a` | **KEEP** |
| `electron_molar_energy_density` | `electron_molar_energy_density` | `452b1796e5f6cb668ab13de65721eb7c85e3f58ef3acc544fb8919ab96463a3a` | **KEEP** |
| `electron_physical_energy_density` | `electron_energy_density_eV_m3` | `77a496774cef51d3905b90fdcb98da8e261d4c3969622508aa19a53481bf2ccc` | **KEEP** |
| `electron_physical_density` | `n_e_physical` | `33f68912653aaba28a9fd27353dc9671538c180a8e1d9accabb5c6e69e3e8b17` | **RETIRE ONLY IN P3-X** |
| `electron_wall_flux` | `e_wall_number_flux` | `cd1be5c26c3f72ec0e42d36d342849918d48c02a2a609543c15db045309d6824` | **RETIRE ONLY IN P3-X** |

Existing `electron_molar_energy_density` and `electron_energy_density_eV_m3` are **distinct** from Physics `ElectronEnergyMaterial::e_energy_eV`; do not retire them just because their names contain “energy”. Preserve their existing consumer edges.

## Physics New-only generator contracts

- `DDEnergyEq.C` creates `ElectronEnergyMaterial` producing `e_energy_eV=exp(log_e_energy-log_e)` from the single electron state.
- `DDContinuityEq.C` creates one `DDTransportMaterial(species_id=e)` from typed JSON `lookup/reduced/clamp` and the original 42-row table. It publishes `e_mobility/e_diffusivity`, historical aliases, and `e_energy_mobility/e_energy_diffusivity = (5/3)×e particle coefficients` under `[Energy] transport_coefficient=fluid`.
- `DDEnergyEq.C` also creates `n_e_physical` and `ESWallFluxMaterial(species_id=e)` yielding `e_wall_number_flux`. The existing old C0 two Functor producers above **would collide** with those new Physics owners.
- In the actual 11-layer New-only input there is **no explicit** `e_energy_eV` or `DDTransportMaterial(species_id=e)` block, so there is no extra static owner for those two producer *classes*.
- New-only JSON creates eight FEM electron BCs; do not retain the original eight BC owners simultaneously.

## Independent source-byte proof

- Both cases: 11/11 exact file SHA and 5/5 direct FunctorMaterial owner block SHA; 12/12 source negative mutations rejected *per case*.
- Existing P3-X isolated disposable-copy **10-owner** removal (8 BCs plus the two conflicting FunctorMaterials) re-run and byte-compared to shadow ZIP, C0 before `39826e1e95372d226cca4036b520a7f13dfd79c8b6ef0ca2d7c0ca49f904e17e` → after `d78a084434eca25b9ece07138c49bf93800845f5947f5ec327bfc81334daa17a`. Other ten .i layers and JSON/table bytes unchanged in each case.
- Runnable independent verifier: `p3_g6_verify_exact_functors.py` (local SHA256 `6d72d3898e4926e380d06bd9b76d4689655d1901090a3918bce259e7bccf6da7`). Local full result JSON SHA256 `b38c98d4e8e826864139fd0b597d302b2d4c7e9c5d39b5798d2672f1562f147f`.
- Detailed committed evidence: [P3-G6 receipt](p3-g6-electron-functor-producer-receipt.json).

**Hold:** This worker has **not** edited PR #665, P2 Production Runner, or the P3-X integrator branch. Actual C++ Warehouse singleton Functors, dynamic EI/Poisson/RF/neutral consumers, and Native `--check-input` remain unverified. Native P2/P3/P4 NOT_RUN; `SCIENCE_HOLD`. P3-X must integrate this G6 receipt under its single-writer gate.
