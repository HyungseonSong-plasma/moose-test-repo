# P4-X Stage 1 — guarded source-only owner handoff (partial)

**Status:** `PASS_DISPOSABLE_STATIC / NOT_IN_PRODUCTION_RUNNER / SCIENCE_HOLD`  
**Task:** #670 P4-X, after P2 #668 and P3-X #669, never Native scientific P4.

## Pin and exact outputs

- Current Draft #665 integration HEAD at test: `395eeac274125ffa632b4d75a4531996dee24fe0`.
- The **input bytes** remain pinned to original 11-layer source HEAD `9c15a4f0e2cf8042cb0d4b2f18af31511021d168`; don't silently claim the source CI ran against the newer merge HEAD.
- Source CI `44257739203`, artifact `14406746397`, ZIP SHA256 `592a7c82834bab841f6a2e1807db305d0eff1e953f50a0dcc6d7e21ff8820111`.
- Both S6-417 and S6-941 have P3-X staged C0 SHA256 `d78a084434eca25b9ece07138c49bf93800845f5947f5ec327bfc81334daa17a`, and 11/11 pinned `.i` SHA checks. The proposed **one-file-only** C0 after-SHA is `2c3bab8a8e28b360dcd54775d91ba13c97401364c709944bc21d6bf0b6d79490` in both cases. Other 10/10 layers byte-identical.
- [Full 2-case source-only Stage 1 receipt](partial_static_receipt.json) has all exact seven block SHA and status gates.

## Only allowable Stage 1 changes inside disposable Scratch

1. In `[FunctorMaterials]/constants` replace the *exact SHA-pinned* seven-property object body by the same `ADGenericFunctorMaterial` with **only** `prop_names = 'carrier_one'`, `prop_values = '1.0'`, and `block = plasma`. This retires the six now-Physics-owned `O2p/Om/Op_mobility,diffusivity` Functor outputs, preserving the non-target carrier.
2. Remove only the exactly pinned `[FunctorMaterials]/ion_wall_flux`, `negative_ion_wall_flux`, `atomic_positive_ion_wall_flux`. They were shadow providers of the three canonical `<species>_wall_* ` Functor groups; `Chemistry.C` is the intended new material owner, and the original signed charges are `(+1,-1,+1)`.
3. Remove only the exactly pinned `[FunctorMaterials]/cover_surface_current`, `wafer_surface_current`, `focus_ring_surface_current`. They produce the same `1.602176634e-19*(gi+gop-gm-ge)` source as the new Physics owner.
4. **Never delete or modify** `n_i_physical/n_m_physical/n_op_physical` aliases, `charge_number_density`, Poisson source, Lower-D sigma/time/current/BC objects or observers, electron/neutral/RF/pressure owners, or protected raw EI/H25 rate files.
5. Preconditions: exact 11 canonical staged file SHA, case-local New-only JSON and overlay byte SHA, required `.issue633_disposable_scratch` marker, regular-file/no-symlink checks, exact seven `(FunctorMaterials, object_name, block_sha)` matches, JSON charge/mass/transport/BC contract, `wall_gradient=adjacent_element` and `migration_smoothing_width=0.001`. Fail closed **before any write**. Default is dry run; only an explicit `--apply` may atomically rewrite the C0 scratch file.

## Reproduction and static negative suite

A standard-library-only working implementation (`retire_s6_p4_stage1_owners.py`, SHA256 `c8ccd4bb5603e5bc2736c262d365ae4393f7e8c11daad62cf7d3a7adff74b0fb`) and independent artifact replay verifier (`replay_verify.py`, SHA256 `2127d8965bbd27f1b4be8430195531ca31697f2e2ce5009d8401cdadf78774bc`) were executed in isolated local copies of the CI archive. Both cases passed dry-run and guarded apply, and **14/14 malicious variations were rejected with no file change**. The scripts have **not** been merged into the repository runner; the receipt records the exact code digests for custody.

## P5/Native blocker observed during this work

[Diagnostic CI #44262035027](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/44262035027) completed its diagnostic *workflow*, but the actual `--check-input` calls returned **exit 1** for **both** cases, before material/BC Warehouse checks:

```
Unable to open file "/case/experiments/Issue395_powered_chemistry_ladder/baseline_plasma_plus_unstructured_cover_plus_wafer.msh-mesh.cpa.gz"
```

Do not mistake this for a validated P4-X/Native P2 rejection caused by duplicate Functors; the missing **parent plasma mesh** blocks reaching that stage. The already-staged **Maxwell child QVT mesh** is a different file. Exact diagnostic artifact: #14408333164.

## Subsequent gates

- Decide and integrate `Source 5→3` signed rate aggregation, preserve ion density/Poisson and dependent diagnostics/Lower-D consumers, and reconcile the full 35 worker receipts before full P4-X authorization.
- Call the guarded Stage1 cutover within the **real** production `prepare_s6_run_input.py --newonly` only after reviewing the complete P4-X contract, then independently rerun both 11-layer builds and all negative gates.
- Stage the missing parent plasma mesh with its own original SHA custody and retry guarded Native `--check-input` in P5 #671. Separately establish generated three ion Wall Material, six coefficient, three surface current and 12 FVBC *runtime* single ownership.
- P5 Native P2, Native P3/P4 and scientific equivalence **remain NOT RUN / HOLD**. No protected source, main, #665, workflows or raw private Rate data changed by Stage1.
