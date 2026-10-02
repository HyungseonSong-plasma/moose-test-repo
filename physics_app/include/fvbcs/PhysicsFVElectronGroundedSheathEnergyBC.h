#pragma once

#include "FVQpFluxBC.h"

/**
 * Primary-electron energy collection at a grounded conducting wall for the
 * accepted sheath-unresolved electron-repelling branch.
 *
 * Legacy normalized mode returns
 *
 *   Gamma_eps_hat,out
 *     = (Gamma_e,p,out / n_ref)
 *       * (alpha T_e[eV] + Delta phi[V]) / epsilon_ref[eV].
 *
 * Physical-eV mode interprets electron_density as n_e [1/m^3] and returns
 * the conservative energy flux directly in [eV/(m^2 s)].
 *
 * T2 molar-energy mode instead interprets electron_density as c_e [mol/m^3]
 * and returns the conservative energy flux directly in [eV mol/(m^2 s)]:
 *
 *   Gamma_c_eps,out
 *     = Gamma_e,p,out[mol/(m^2 s)] * (alpha T_e[eV] + Delta phi[V]).
 *
 * alpha is supplied by the energy_per_particle_te_factor functor. The default
 * alpha=2 preserves the kinetic half-Maxwellian sheath closure; callers may
 * explicitly supply another closure (for example alpha=5/2 in a transport-
 * matched diffusion diagnostic).
 *
 * Both modes use exactly the shared W4 primary-particle sheath relation.
 * Ion-induced SEE energy remains a separate inward owner.
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
  const Moose::Functor<ADReal> & _energy_per_particle_te_factor;
  const Real _energy_reference_eV;
  const bool _molar_energy_state;
  const bool _physical_eV_state;
};
