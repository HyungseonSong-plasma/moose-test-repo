#pragma once

#include "FunctorMaterial.h"

/**
 * Electron mean-energy bridge.
 *
 * Physical formulation:
 *   mean_en = electron_energy_density / electron_density [eV].
 *
 * Log-molar formulation:
 *   eta_n = ln[(n_e/N_A)/(1 mol/m^3)]
 *   eta_eps = ln[(w_e/N_A)/(1 eV mol/m^3)]
 *   mean_en = exp(eta_eps - eta_n) [eV].
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
  const bool _log_molar_state;
  const Moose::Functor<ADReal> & _electron_energy_density;
  const Moose::Functor<ADReal> & _electron_density;
  const Real _energy_reference_eV;
};
