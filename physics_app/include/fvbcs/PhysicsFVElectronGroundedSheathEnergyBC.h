#pragma once

#include "FVQpFluxBC.h"

/**
 * Primary-electron energy collection at a grounded conducting wall for the
 * accepted sheath-unresolved electron-repelling branch.
 *
 * Optional particle-subgrid mode reuses the same 1D drift-diffusion primary-particle
 * closure as the particle BC. Optional energy-subgrid mode additionally solves the
 * constant-coefficient 1D energy drift-diffusion closure between the FV centroid and
 * wall, so the wall energy per collected electron is inferred from a subcell energy
 * state instead of the coarse cell-center mean energy.
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
  const Moose::Functor<ADReal> * _electron_energy_density;
  const Moose::Functor<ADReal> * _energy_mobility;
  const Moose::Functor<ADReal> * _energy_diffusion;
  const Real _energy_reference_eV;
  const bool _molar_energy_state;
  const bool _physical_eV_state;
  const bool _apply_sheath_suppression;
  const bool _use_wall_subgrid_closure;
  const bool _use_wall_energy_subgrid_closure;
  const Real _charge_number;
};
