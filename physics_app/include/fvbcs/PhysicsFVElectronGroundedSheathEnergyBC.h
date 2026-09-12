#pragma once

#include "FVQpFluxBC.h"

/**
 * Primary-electron energy collection at a grounded conducting wall for the
 * accepted sheath-unresolved electron-repelling branch.
 *
 * The plasma-side FV cell is the sheath edge.  The normalized outward energy
 * flux is
 *
 *   Gamma_eps_hat,out
 *     = (Gamma_e,p,out / n_ref)
 *       * (2 T_e[eV] + Delta phi[V]) / epsilon_ref[eV],
 *
 * using exactly the shared W4 primary-particle sheath relation.  Ion-induced
 * SEE energy remains a separate inward owner.
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
  const Real _energy_reference_eV;
};
