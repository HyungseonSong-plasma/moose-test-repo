#pragma once

#include "FunctorMaterial.h"

#include <string>
#include <vector>

/**
 * Coupling layer for the plasma charge core.
 *
 * Heavy charged species:
 *   primary variable = heavy-species mass fraction w_k
 *
 * Electron:
 *   primary variable = number density n_e [1/m^3]
 *
 * Derived ion number density:
 *   n_k = rho * w_k * N_A / M_k
 *
 * Charge density:
 *   rho_q = e * (sum_k z_k n_k - n_e)
 *
 * Electric field:
 *   E = -grad(phi)
 *
 * Heavy-species electromigration uses a mass-average correction:
 *
 *   V_c = - sum_k w_k z_k mu_k E
 *
 * so every independent heavy species receives V_c, while charged heavy
 * species additionally receive z_k mu_k E. The constrained neutral remainder
 * then carries the corresponding inferred correction flux and the total heavy
 * relative mass flux sums to zero.
 */
class PhysicsPlasmaChargeTransportMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  PhysicsPlasmaChargeTransportMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _potential;
  const Moose::Functor<ADReal> & _density;
  const Moose::Functor<ADReal> & _electron_density;
  const Moose::Functor<ADReal> & _electron_mobility;

  std::vector<std::string> _ion_ids;
  std::vector<MooseFunctorName> _ion_mass_fraction_names;
  std::vector<const Moose::Functor<ADReal> *> _ion_mass_fractions;

  std::vector<Real> _ion_molar_masses;
  std::vector<Real> _ion_charges;

  std::vector<MooseFunctorName> _ion_mobility_names;
  std::vector<const Moose::Functor<ADReal> *> _ion_mobilities;

  std::vector<MooseFunctorName> _ion_diffusion_names;
  std::vector<const Moose::Functor<ADReal> *> _ion_diffusions;
};
