#pragma once

#include "FVElementalKernel.h"

/**
 * Electron-energy electric-work source for direct physical/molar or legacy
 * normalized energy states.
 *
 * The local constitutive electron particle flux is owned by the shared
 * PhysicsElectronFluxModel helper.  The density functor determines the direct
 * unit system:
 *
 *   physical_eV: n_e [1/m^3] -> source [eV/(m^3 s)]
 *   molar_eV:    c_e [mol/m^3] -> source [eV mol/(m^3 s)]
 *
 * Legacy normalized mode retains the historical epsilon_ref division only for
 * compatibility.  New conservative molar-energy paths should use molar_eV.
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
