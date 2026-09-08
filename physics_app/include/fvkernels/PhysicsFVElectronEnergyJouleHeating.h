#pragma once

#include "FVElementalKernel.h"

/**
 * Electron-energy electric-work source for the normalized FV energy equation.
 *
 * With E = -grad(phi) and the normalized electron particle flux
 *
 *   Gamma_e / n_ref = -mu_e n_hat E - D_e grad(n_hat),
 *
 * the normalized electron-energy source is
 *
 *   S_hat = [-E . (Gamma_e / n_ref)] / epsilon_ref
 *         = [mu_e n_hat |E|^2 + D_e E . grad(n_hat)] / epsilon_ref.
 *
 * The kernel contributes -S_hat to the residual so positive electric work is
 * a positive right-hand-side source. The particle equation itself remains
 * owned by PhysicsFVElectrostaticDrift and framework FVDiffusion.
 */
class PhysicsFVElectronEnergyJouleHeating : public FVElementalKernel
{
public:
  static InputParameters validParams();
  PhysicsFVElectronEnergyJouleHeating(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _electron_density;
  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _diffusion;
  const Real _energy_reference_eV;
};
