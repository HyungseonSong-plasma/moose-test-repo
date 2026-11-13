#pragma once

#include "FunctorMaterial.h"

/**
 * Unique electron mean-energy [eV] Functor provider.
 *
 * state_form=log_molar_eV:
 *   e_energy_eV = exp(log_e_energy - log_e)
 *   (molar energy / molar electron density, both states in logarithms).
 *
 * One canonical log-molar state; one fixed output name and no compatibility aliases.
 */
class ElectronEnergyMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  ElectronEnergyMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _electron_energy_density;
  const Moose::Functor<ADReal> & _electron_density;
};
