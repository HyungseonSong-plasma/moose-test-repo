#pragma once

#include "FVQpFluxBC.h"

/**
 * Primary-electron energy collection at a grounded conducting wall for the
 * accepted sheath-unresolved electron-repelling branch.
 *
 * Optional wall-subgrid mode reuses the same 1D drift-diffusion primary-particle
 * closure as the particle BC, then multiplies that particle flux by the sheath
 * energy carried per collected electron. This keeps particle and energy wall
 * losses tied to one effective unresolved wall state.
 */
class PhysicsFVElectronGroundedSheathEnergyBC : public FVQpFluxBC
{
public:
  static InputParameters validParams();
  PhysicsFVElectronGroundedSheathEnergyBC(const InputParameters & parameters);

protected:
  ADReal computeQpResidual() override;

  const Moose::Functor<ADReal> & _electron_density;
  const Moose::Functor<ADReal> & _mean_electron_energy;
  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> * _mobility;
  const Moose::Functor<ADReal> * _diffusion;
  const Real _energy_reference_eV;
  const bool _molar_energy_state;
  const bool _physical_eV_state;
  const bool _apply_sheath_suppression;
  const bool _use_wall_subgrid_closure;
  const Real _charge_number;
};
