# Root-cause diagnosis — BOLSIG+ vs C++ CI EEPF (Example 4, 2026-10-28)

**Conclusion:** Earlier C++ orange dashed curves are native C++ computations on *manufactured constant elastic-only collision tables*. They are not true BOLSIG+ process-matched predictions. Treat any discrepancy as a **model and data setup mismatch**, not direct evidence of an incorrect discretization.

## Same external labels but different physical operators

Both curves used E/N=10 Td, T_g=300 K, Ar/He/N2/O2=0.70/0.20/0.08/0.02 and the BOLSIG+ selected Emax=15.8367 eV. The C++ CI source is physics_app/ci/boltzmann_ci_eepf_controls.C and uses invented constant sigma_m=5e-20 m² for all four species, omits all excitation, ionization, attachment, and actual EFFECTIVE process semantics. BOLSIG+ uses the PHELPS/SIGLO 04Jun2013 records: **47 processes** including 25 N2 processes and 16 O2 processes, and non-constant effective momentum cross sections for Ar/He/O2.

The official BOLSIG+ manual (07/2024) defines EFFECTIVE as a cross section already including total elastic **and inelastic** momentum scattering for the named gas. It must not be interpreted as a pure ELASTIC cross section and then added to all excitation cross sections: that double counts scattering. See https://www.bolsig.laplace.univ-tlse.fr/wp-content/uploads/2024/07/bolsigdoc0724.pdf p.9.

## Exact evidence from uploaded native example4-eepf.dat

- Native BOLSIG+ EEPF is normalized: trapezoid integral of sqrt(E)*f(E) over printed adaptive grid = 0.999866 (minor omitted endpoints).
- Its independently integrated mean energy is 1.356912 eV, matching native header 1.35694 eV. Thus EEPF versus EEDF terminology or normalization is not the cause.
- Native Emax=15.8367 eV; 195 output grid points, nonuniform. C++ developer EEPF uses 200 uniform cells with same Emax.
- Native BOLSIG+ f(last)/f(first) = 1.30e-10, i.e. distribution decayed strongly at upper boundary.
- CI C++ synthetic f(last)/f(first) = 0.4834, i.e. the tail remains nearly half its low-energy amplitude at the same Emax. Zero-flux boundary then causes a **severe energy truncation artifact**.
- Native BOLSIG+ fraction of electrons above 5 eV ~2.07%, above 10 eV ~0.0086%; C++ synthetic ~77.0% and ~40.5% respectively. Reported using trapezoidal integration of sqrt(E)*EEPF on each printed output's own grid; the C++ native cell-exact values are ~77.02% and ~40.60%.
- Mean energy is 1.35694 eV for BOLSIG+ versus 8.636201906 eV for native C++ CI synthetic model, factor 6.3645.

## Energy-collision budget local arithmetic

BOLSIG+ Example 4 reported power input/N=4.37845e-16 eV m³/s, elastic loss/N=5.24780e-18, inelastic loss/N=4.32630e-16, growth power/N=5.88346e-24.

From the 47 printed per-process energy loss coefficients, each multiplied by its gas mole fraction:

- N2 EXCITATION loss/N=4.2136452568176e-16 eV m³/s = **97.396%** of reported inelastic loss.
- O2 EXCITATION loss/N=1.1312423902e-17 = **2.615%**.
- Ar EXCITATION loss/N=1.726571e-20 = 0.00399%.
- Total excitation process output components sum to ~4.326942e-16, ~0.01484% greater than the separate printed inelastic loss; small differing output/accounting conventions and finite digits are **not** silently fitted away.
- The inelastic loss is ~98.81% of reported electric input. Native BOLSIG+ three-body O2 attachment and temporal growth exist but growth power is only ~1.3e-6 percent of total input power in this case and **cannot** account for the huge mean-energy discrepancy on its own.

**Immediate diagnosis: N2 vibrational/low-threshold excitation cooling is the dominant missing channel.** O2 excitation is secondary. The 0.02–2.35 eV N2 ladder is particularly relevant to low-energy EEPF shape.

## Controlled C++ ablations — preserve same numerical solver

1. Original first-party synthetic constant elastic sigma=5e-20 m², with Emax=15.8367 eV and 200 energy cells -> mean=8.636201906 eV.
2. Same synthetic collision physics and **same energy cell width**; Emax 31.6734 eV / 400 cells -> mean=12.978517721 eV; 63.3468 eV / 800 cells -> mean=13.715549009 eV; 126.6936 eV / 1600 cells -> mean=13.715750856 eV. The original 15.84 eV energy ceiling is **not converged** for this synthetic elastic model. The boundary artifacts make *its measured* mean energy smaller, not more BOLSIG-like after convergence.
3. Locally derive an *illustrative momentum-only proxy* by reading the Ar/He/O2 EFFECTIVE and N2 ELASTIC tables echoed in the user's original example4.dat, and temporarily feeding those tabulations into the same C++ elastic solver **without inelastic channels** (not a self-consistent physical model). With Emax=15.8367 eV / 200 cells, mean=7.175546985 eV; at 31.67/400 cells, 8.425136344 eV; at 63.35/800 cells, 8.617220535 eV; 126.69/1600 cells, 8.619105985 eV. Thus actual energy-dependent momentum scattering *alone* does not explain the needed ~1.36 eV result. Crucially, these EFFECTIVE tables cannot simply be used as ELASTIC with excitation momentum added, because that would double count.

The more fundamental mistake in the previous comparison workflow was prematurely presenting physics-mismatched models as a visual parity check. The correct next development order is: adopt real source-provenance checked complete 47-process data; implement EFFECTIVE semantics without momentum double counting; add low-threshold N2/O2 excitations with conservative energy transfer and inverse-process populations; add growth/attachment semantics; then auto-adjust Emax until EEPF tail and moments converge; finally compare EEPF and transport with BOLSIG+ at matched conditions. A change to the plotting palette or EEPF normalization cannot repair a mismatched collision operator.

**Safety:** no uploaded original third-party cross section tables are committed, and no production MOOSE closure should be changed or PR 408 promoted on the basis of these diagnostics.

## S6 exact-head live GitHub Actions evidence

[Repository CI run 40681830605](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40681830605), committed at 27808688e1fee643d474418872e387865cbfdf4a, ran its independent **Native Boltzmann EEPF development controls** job successfully. Its produced [artifact 12813151424](https://github.com/HyungseonSong-plasma/moose-test-repo/actions/runs/40681830605/artifacts/12813151424) contains **nine real C++-executed EEPFs** and the manifest's domain-truncation evidence:

- relative change of mean between 15.8367 and 31.6734 eV domains (relative to latter) = 0.3345771765;
- relative change between 63.3468 and 126.6936 eV domains (relative to latter) = 1.4716452e-5;
- explicit classification 1X_ENERGY_DOMAIN_TRUNCATION_HOLD.

This verifies the local cutoff ablation directly in GitHub Actions. Normalized flux residual in the zero-flux synthetic steady model remained <1e-14 even when the energy cutoff was grossly inadequate; **small linear-system residual is not a domain-convergence guarantee**. Changing synthetic electron/neutral mass ratios to match input table values changed the 15.84 eV mean from 8.6362 to 8.6423 eV (0.07%); this is not the missing physics.
