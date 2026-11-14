# Issue402: EI10/EI16 owner reduction and heavy-rate retention

Date: 2026-11-13. PR #524, Draft, unmerged. S6 P3/P4 NOT_RUN. SCIENCE_HOLD.

## Existing dedicated object migration (1--3)

Four owner classes were replaced in current native fixture inputs and in the
Stage-5 input generator. Their historical contracts are retained as evidence.

| Old owner | New owner | Physical positive-domain contract |
| --- | --- | --- |
| PhysicsElectronImpactO2sExcitationMaterial | ADParsedFunctorMaterial | R_O2s = 4.71e8*(ne/6.02214076e23)*cO2 |
| PhysicsElectronImpactIonizationMaterial | PhysicsElectronImpactRateMaterial | Strict mean-energy interpolation; output R_ion_O2 |
| PhysicsO2sExcitationSourceMaterial | Two ADParsedFunctorMaterials | O2 mass=-0.031998*R_O2s; O2s mass=+0.031998*R_O2s |
| PhysicsO2IonizationSourceMaterial | Three ADParsedFunctorMaterials | O2 mass=-0.031998*R_ion_O2; O2p mass=+0.031998*R_ion_O2; electron number=6.02214076e23*R_ion_O2 |

The replacement preserves canonical progress and source names, normal-domain
AD algebra and physical units. It does not claim equivalence for invalid
inputs: original EI10 classes explicitly raised errors for negative
concentrations/progress; parsed algebra does not independently reproduce
that exception surface. Generic EI16 rate does reject negative lookup
coefficients, as well as out-of-range mean energies. This difference is
an explicitly OPEN invalid-state semantic question.

Stage-5 producer: experiments/historical_recipe_support/issue192_s5r.py.
Other migrated EI16 producer:
experiments/Issue395_powered_chemistry_ladder/build_o2_ionization_overlay.py.
Updated source-backed R2/R3/E8/standard-MOOSE fixtures cover the canonical
positive-state oracles. Earlier source-only CI #43428302896 passed 25
targeted tests plus EI10/EI16/Stage-5 checks before factory deletion.
Native after-deletion acceptance must use exact-source P1/P2 plus
bounded controlled R2/R3/E8 numeric fixtures; it is separate from S6 P3.

## Why PhysicsReactionRateMaterial (4) remains

S5-D uses physics_app/data/heavy_reactions/stage5_s5d_oxygen_heavy.txt
for H01--H04. S5-E uses stage5_s5e_h05_oxygen_heavy.txt for H05.
The Stage-5 generator retains two PhysicsReactionRateMaterial instances.

PhysicsReactionDatabase validates the reaction species catalogue, heavy
vs electron classification, active volume reaction subset, duplicate
names and charge/mass conservation. Particle-basis reaction-rate
prefactors are converted to molar basis by N_A^(order-1).

The heavy rate Material calculates:
    R_j = A_molar * (T_ref/T_g)^p * product_i (rho*w_i/M_i)^nu_ij.
It publishes one reaction_rate_<database_name> Functor per reaction;
downstream source consumers reuse that single progress producer.

For H05 (Om + O -> O2 + electron), the electron is a PRODUCT solely
for charge conservation accounting; the separate electron source is
positive, with no H05-specific electron-energy source by accepted
Stage-5 convention.

PhysicsSurfaceReactionMaterial also uses PhysicsReactionDatabase.
Do not remove their shared parsing/validation functionality without
a separate surface-chemistry compatibility evaluation.

The new Physics Chemistry model validates ID, stoichiometry, energy
loss and projects existing R_Hxx to signed species/energy Functors;
it does NOT yet parse Stage-5 heavy rate files or synthesize the
A_molar, power-law temperature and mass-fraction concentration model.
The S6 H25 analytic rate is not a general H01--H05 substitute.

Decision: RETAIN PhysicsReactionRateMaterial without code edits.
Possible future removal requires a real replacement heavy-rate owner,
unit/prefactor/parity validation, active-reaction selection semantics,
charge/mass/duplicate guards, H05 electron/energy convention, and
Native A/B at multiple temperatures. SCIENCE_HOLD remains.
