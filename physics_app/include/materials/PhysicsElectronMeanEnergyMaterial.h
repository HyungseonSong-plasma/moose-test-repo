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
 * By default this material is strict and does not floor or clamp the solved
 * state. An opt-in nonlinear-trial fallback is available for segregated
 * multirate solves so invalid intermediate Newton iterates do not abort before
 * line search can recover a physical state. The converged state remains subject
 * to the normal positivity diagnostics.
 */
class PhysicsElectronMeanEnergyMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsElectronMeanEnergyMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _electron_energy_density;
  const Moose::Functor<ADReal> & _electron_density;
  const Real _energy_reference_eV;
  const bool _use_trial_state_fallback;
  const Real _trial_fallback_mean_energy_eV;
};
