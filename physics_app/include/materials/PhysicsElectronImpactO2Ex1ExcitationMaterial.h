#pragma once

#include "FunctorMaterial.h"

/**
 * Reaction 411, e + O2(X3Sigma_g-) -> e + O2(ex1), 4.5 eV excitation.
 *
 * One canonical molar progress:
 *   R_O2_ex1_411 = (N_A k_particle(Te)) (n_e/N_A) c_O2 [mol/(m^3 s)]
 *   k_particle(Te) = 1.07e-15 exp(-3.43/Te) [m^3/s]
 *   Te [eV] = (2/3) mean_en_solved [eV].
 *
 * The fit assumes a Maxwellian EEDF and is valid for 1 <= Te <= 7 eV.
 * Source: Gudmundsson et al., J. Phys. D: Appl. Phys. 33 (2000)
 * 1323-1331, Table 3, https://doi.org/10.1088/0022-3727/33/11/311.
 *
 * O2(ex1) is not a resolved heavy species in the current powered ICP.
 * This material owns the single rate only. Its sole active downstream
 * projection is -4.5 eV per event into the electron-energy equation.
 * No O2, O, charged-species or electron-number source is produced.
 */
class PhysicsElectronImpactO2Ex1ExcitationMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsElectronImpactO2Ex1ExcitationMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _electron_number_density;
  const Moose::Functor<ADReal> & _o2_molar_concentration;
  const Moose::Functor<ADReal> & _mean_energy;
};
