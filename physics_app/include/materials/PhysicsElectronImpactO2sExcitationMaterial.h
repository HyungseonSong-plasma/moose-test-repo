#pragma once

#include "FunctorMaterial.h"
#include "MooseEnum.h"

/**
 * Canonical Stage-3 rate owner for e + O2 -> e + O2(a1Delta_g).
 *
 * R_O2s = k(Te) * (n_e / N_A) * c_O2 [mol/(m^3 s)]
 * k(Te) = N_A * 1.37e-15 * exp(-2.14/Te) [m^3/(mol s)], Te = 2/3 mean_en_solved.
 * The 1-7 eV Maxwellian fit is from Gudmundsson et al. (2000), Table 3,
 * https://doi.org/10.1088/0022-3727/33/11/311.
 *
 * A legacy constant-surrogate mode is retained solely for reproducing bounded
 * historical discriminators; the production Stage-5 EI10 assembly opts into
 * temperature_dependent. All downstream sources consume one shared R_O2s.
 */
class PhysicsElectronImpactO2sExcitationMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsElectronImpactO2sExcitationMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _electron_number_density;
  const Moose::Functor<ADReal> & _o2_molar_concentration;
  const MooseEnum _rate_model;
  const Moose::Functor<ADReal> * _mean_energy;
};
