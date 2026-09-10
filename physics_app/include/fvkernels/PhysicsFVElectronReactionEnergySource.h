#pragma once

#include "FVElementalKernel.h"

/**
 * Projects one existing canonical molar reaction progress into the normalized
 * electron-energy equation without evaluating reaction kinetics.
 *
 * For R [mol/(m^3 s)] and a positive electron energy loss Delta_epsilon [eV]
 * per reaction event,
 *
 *   S_epsilon = -Delta_epsilon * N_A * R              [eV/(m^3 s)]
 *   S_hat     = S_epsilon / (n_ref * epsilon_ref)     [1/s]
 *
 * and the FV residual contribution is -S_hat. Therefore a positive reaction
 * progress with positive energy loss contributes a positive residual (an
 * electron-energy sink on the right-hand side).
 *
 * This kernel intentionally consumes an upstream reaction_progress functor;
 * it must never become an independent kinetic-rate owner.
 */
class PhysicsFVElectronReactionEnergySource : public FVElementalKernel
{
public:
  static InputParameters validParams();
  PhysicsFVElectronReactionEnergySource(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _reaction_progress;
  const Real _energy_loss_eV;
  const Real _n_ref;
  const Real _energy_reference_eV;
};
