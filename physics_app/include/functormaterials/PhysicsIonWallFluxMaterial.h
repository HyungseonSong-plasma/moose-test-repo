#pragma once

#include "FunctorMaterial.h"

/**
 * Positive outward ion wall-loss flux.
 *
 * Surface component:
 *
 *   Gamma_s = s * (1/4) * n_i * sqrt(8 R T_g / (pi M_i))
 *
 * Migration component:
 *
 *   Gamma_m = n_i * mu_i * max(z_i E_n, 0)
 *
 * with E = -grad(phi) and E_n = E . n_out.
 *
 * The generated functors are:
 *
 *   ion_surface_number_flux
 *   ion_migration_number_flux
 *   ion_wall_number_flux
 *   ion_surface_mass_flux
 *   ion_migration_mass_flux
 *   ion_wall_mass_flux
 *
 * These wall-flux functors are intentionally face-only. Non-face evaluations
 * return zero. FV wall boundary conditions and surface-charge bookkeeping
 * should evaluate them with a sided FaceArg so that the same physical face
 * flux is shared by all consumers.
 */
class PhysicsIonWallFluxMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsIonWallFluxMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _ion_number_density;
  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _mobility;
  const Moose::Functor<ADReal> & _gas_temperature;

  const Real _charge_number;
  const Real _molar_mass;
  const Real _sticking;
  const Real _migration_gate_smoothing_width;
};
