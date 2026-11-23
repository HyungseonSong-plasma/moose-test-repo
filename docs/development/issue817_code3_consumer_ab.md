# Code3 D3 — H05/R2/S5-R consumer-specific source A/B

Issue #817, stacked over Draft #818 at 0772153070bb592d53d835d5fdb81da76280f77d. This preparation retains the original C/H, Factory, generator/checker contracts and production CI. No source is retired.

- H05: original runtime_input() with the existing Issue402 exact physical-to-log-molar ElectronEnergyMaterial bridge applied to both arms; only electron source block changes to FVCoupledForce(v=S_e_h05, coef=1).
- R2: original controlled ionization fixture plus a guarded physical-to-log-molar energy representation bridge applied to both arms; only electron source block changes to FVCoupledForce(v=electron_ionization_number_source, coef=1). The original reaction table is unchanged.
- S5-R: original currently imported issue192_s5r.build_s5r_input(heavy_base.i) must pass original audit, then only the electron source block changes to FVCoupledForce(v=S_e_s5r, coef=1/n_ref). This does not modify the live S5-R generator or its old-type checker.

A common representation bridge is not a claimed electron-source equivalence: comparisons are always made between bridged old/candidate inputs. Exact outside-block byte identity is mandatory. The source-prep and negative P0 gates are not Native P2/P3, AD Jacobian, charge/energy source closure, or global consumer deletion approval. Source C/H deletion and merge remain HOLD until all live generators/CI consumers are migrated with independent science evidence. Temporary one-shot Actions workflows must be removed before any integration; preserve their run artifacts.
