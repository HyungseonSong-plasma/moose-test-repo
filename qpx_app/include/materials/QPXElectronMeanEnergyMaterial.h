#pragma once

#include "FunctorMaterial.h"

/**
 * Canonical solved electron mean-energy bridge for the normalized FV system.
 *
 * The conserved normalized states are
 *
 *   n_e_phys       = n_ref * n_e_hat
 *   n_epsilon_phys = n_ref * epsilon_ref * n_epsilon_hat
 *
 * so the local solved mean energy is
 *
 *   mean_en_solved = epsilon_ref * n_epsilon_hat / n_e_hat [eV].
 *
 * epsilon_ref is a normalization scale only. This material deliberately does
 * not floor the denominator or clamp the resulting mean energy; invalid state
 * rejection and lookup bounds remain explicit numerical contracts.
 */
class QPXElectronMeanEnergyMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  QPXElectronMeanEnergyMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _electron_energy_density;
  const Moose::Functor<ADReal> & _electron_density;
  const Real _energy_reference_eV;
};
