#pragma once

#include "FVElementalKernel.h"

/**
 * Electron-energy electric-work source for physical-number-density, molar-density,
 * or legacy normalized electron states.
 *
 * The local constitutive electron particle flux is owned by the shared
 * PhysicsElectronFluxModel helper.  The numerical units follow the density functor:
 *
 *   physical_eV : n_e [1/m^3]   -> source [eV/(m^3 s)]
 *   molar_eV    : c_e [mol/m^3] -> source [eV mol/(m^3 s)]
 *   normalized  : historical normalized density and epsilon_ref scaling.
 *
 * The particle FV face reconstruction remains owned by the particle flux kernels;
 * this kernel reuses the same constitutive flux model rather than duplicating its algebra.
 */
class PhysicsFVElectronEnergyJouleHeating : public FVElementalKernel
{
public:
  static InputParameters validParams();
  PhysicsFVElectronEnergyJouleHeating(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const bool _normalized_state;
  const Moose::Functor<ADReal> & _electron_density;
  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _diffusion;
  const Real _energy_reference_eV;
};
