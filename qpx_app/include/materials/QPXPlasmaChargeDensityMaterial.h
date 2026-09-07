#pragma once

#include "FunctorMaterial.h"

#include <string>
#include <vector>

/**
 * Charge-density closure for the FV plasma electrostatic equation.
 *
 * Heavy charged species are supplied as mass fractions:
 *
 *   n_k = rho * w_k * N_A / M_k
 *
 * Electron is supplied directly as number density n_e.
 *
 * The material provides:
 *
 *   charge_number_density = sum_k z_k n_k - n_e
 *   charge_density        = e * charge_number_density
 *   poisson_charge_source = charge_density / eps_0
 *
 * so the scaled electrostatic equation is
 *
 *   -div(epsilon_r grad(phi)) = poisson_charge_source.
 *
 * This object deliberately contains no mobility, diffusion, or drift physics.
 */
class QPXPlasmaChargeDensityMaterial : public FunctorMaterial
{
public:
  static InputParameters validParams();
  QPXPlasmaChargeDensityMaterial(const InputParameters & parameters);

protected:
  const Moose::Functor<ADReal> & _density;
  const Moose::Functor<ADReal> & _electron_density;

  std::vector<std::string> _ion_ids;
  std::vector<MooseFunctorName> _ion_mass_fraction_names;
  std::vector<const Moose::Functor<ADReal> *> _ion_mass_fractions;

  std::vector<Real> _ion_molar_masses;
  std::vector<Real> _ion_charges;
};
