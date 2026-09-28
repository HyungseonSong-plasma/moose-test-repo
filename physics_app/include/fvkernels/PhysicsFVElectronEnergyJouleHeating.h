#pragma once

#include "FVElementalKernel.h"

/**
 * Electron-energy electric-work source for the normalized FV energy equation.
 *
 * The local constitutive electron particle flux is owned by the shared
 * PhysicsElectronFluxModel helper:
 *
 *   Gamma_e / n_ref = -mu_e n_hat E - D_e grad(n_hat)
 *
 * and the normalized electron-energy source is
 *
 *   S_hat = [-E . (Gamma_e / n_ref)] / epsilon_ref.
 *
 * The particle FV face reconstruction remains owned by the particle flux
 * kernels; this kernel reuses the same constitutive flux model rather than
 * duplicating its algebra.
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
