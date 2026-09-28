#pragma once

#include "FunctorMaterial.h"

/**
 * Electron mean-energy bridge.
 *
 * Preferred physical formulation:
 *   mean_en = electron_energy_density / electron_density [eV],
 * where electron_energy_density is [eV/m^3] and electron_density is [1/m^3].
 *
 * Historical normalized formulation remains available for compatibility:
 *   mean_en = epsilon_ref * n_epsilon_hat / n_e_hat.
 */
class PhysicsElectronMeanEnergyMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsElectronMeanEnergyMaterial(const InputParameters & parameters);

protected:
  const bool _physical_state;
  const Moose::Functor<ADReal> & _electron_energy_density;
  const Moose::Functor<ADReal> & _electron_density;
  const Real _energy_reference_eV;
};
