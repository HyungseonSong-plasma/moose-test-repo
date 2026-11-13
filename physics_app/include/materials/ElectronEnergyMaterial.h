#pragma once

#include "FunctorMaterial.h"

/**
 * Unique electron mean-energy [eV] Functor provider.
 *
 * state_form=log_molar_eV:
 *   e_energy_eV = exp(log_e_energy - log_e)
 *   (molar energy / molar electron density, both states in logarithms).
 *
 * state_form=physical_eV:
 *   e_energy_eV = electron_energy_density[eV/m^3] /
 *                 electron_density[1/m^3].
 *
 * No normalized state, output aliases or configurable output name.
 */
class ElectronEnergyMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  ElectronEnergyMaterial(const InputParameters & parameters);

protected:
  const bool _log_molar_state;
  const Moose::Functor<ADReal> & _electron_energy_density;
  const Moose::Functor<ADReal> & _electron_density;
};
